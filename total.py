# 필요한 라이브러리를 불러옵니다.
import pyautogui
import time
import glob
import os
import sys
from PIL import Image
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import json
import re
from enum import Enum, auto
import webbrowser
import tkinter.font as tkFont

# --- 추가 라이브러리 설치 확인 ---
# pynput: 키보드/마우스 제어
try:
    from pynput import mouse, keyboard
except ImportError:
    print("오류: pynput 라이브러리가 필요합니다. 'pip install pynput' 명령어로 설치해주세요.")
    sys.exit()

# pystray: 시스템 트레이 아이콘 기능
try:
    import pystray
    from PIL import Image as PILImage
except ImportError:
    print("오류: pystray 라이브러리가 필요합니다. 'pip install pystray' 명령어로 설치해주세요.")
    sys.exit()


# --- 상수 정의 ---
class ActionType(Enum):
    KEY_DOWN = 'key_down'
    KEY_UP = 'key_up'
    MOUSE_DOWN = 'mouse_down'
    MOUSE_UP = 'mouse_up'
    MOVE = 'move'

class MacroType(Enum):
    FILE = 'file'
    MEMORY = 'memory'
    IMAGE_WAIT = 'image_wait'

class RepeatMode(Enum):
    INFINITE = auto()
    COUNT = auto()
    DURATION = auto()

# --- 이미지 매크로 실행 로직 ---
def execute_image_scan(log_func, image_folder_path, stop_event, pause_event):
    """
    지정된 폴더의 이미지를 한 번 스캔하여 클릭하는 함수.
    성공적으로 하나라도 클릭했는지 여부를 반환합니다.
    """
    config_path = os.path.join(image_folder_path, 'config.json')
    settings = {'confidence_level': 0.7, 'click_interval': 0.1, 'frenzy_mode': False, 'use_search_area': False, 'search_area_coords': None}
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                settings.update(json.load(f))
    except Exception as e:
        log_func(f"⚠️ '{os.path.basename(image_folder_path)}' 폴더의 config.json 로드 실패: {e}")

    confidence = float(settings['confidence_level'])
    interval = float(settings['click_interval'])
    is_frenzy = settings['frenzy_mode']
    search_region = settings['search_area_coords'] if settings['use_search_area'] else None

    search_pattern = os.path.join(image_folder_path, 'image*.png')
    all_files = glob.glob(search_pattern)
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', os.path.basename(s))]
    image_files = sorted(all_files, key=natural_sort_key)

    if not image_files:
        log_func(f"이미지 폴더 '{os.path.basename(image_folder_path)}'에 'image*.png' 파일 없음.")
        return False

    any_image_clicked = False
    for image_path in image_files:
        pause_event.wait() # 일시정지 대기
        if stop_event.is_set():
            log_func("이미지 스캔 중지됨.")
            break
        try:
            img = Image.open(image_path)
            location = pyautogui.locateCenterOnScreen(img, confidence=confidence, grayscale=True, region=search_region)

            if location:
                if is_frenzy:
                    pyautogui.click(location, clicks=3, interval=0.01)
                    log_func(f"✅ ⚡ 3회 클릭: '{os.path.basename(image_path)}'")
                else:
                    pyautogui.click(location)
                    log_func(f"✅ 클릭: '{os.path.basename(image_path)}'")
                any_image_clicked = True
                time.sleep(interval)
        except Exception as e:
            log_func(f"🔥 '{os.path.basename(image_path)}' 처리 중 오류: {e}")

    return any_image_clicked

# --- 매크로 실행 유틸리티 클래스 ---
class MacroExecutor:
    @staticmethod
    def execute_macro_item(item_info, callbacks, stop_event, pause_event, speed, timeout, app=None, tree=None):
        """
        매크로 체인 목록의 단일 항목을 실행합니다.
        성공 또는 계속 진행 가능한 오류 시 True, 중지 또는 치명적 오류 시 False를 반환합니다.
        """
        if app and tree and item_info.get('item_id'):
            app.root.after(0, app.update_tree_selection, tree, item_info['item_id'])

        pause_event.wait()
        if stop_event.is_set(): return False

        macro_type = item_info['type']
        macro_data = item_info['data']
        display_name = item_info['display_name']

        callbacks['log'](f"▶️ '{display_name}' 실행 시작...")

        if macro_type == MacroType.IMAGE_WAIT.value:
            callbacks['log'](f"⌛ '{os.path.basename(macro_data)}' 이미지를 찾는 중 (최대 {timeout}초)...")
            wait_start = time.time()
            found = False
            while not stop_event.is_set() and (time.time() - wait_start) < timeout:
                pause_event.wait()
                try:
                    img = Image.open(macro_data)
                    if pyautogui.locateOnScreen(img, confidence=0.8):
                        callbacks['log'](f"✅ '{os.path.basename(macro_data)}' 발견.")
                        found = True
                        break
                    stop_event.wait(0.5)
                except Exception as e:
                    callbacks['log'](f"🔥 이미지 대기 중 오류: {e}")
                    stop_event.wait(1)
            if not found and not stop_event.is_set():
                callbacks['log'](f"⚠️ 시간 초과: '{os.path.basename(macro_data)}'를 찾지 못했습니다.")
        else:  # FILE or MEMORY
            actions = macro_data if macro_type == MacroType.MEMORY.value else callbacks['load_actions_from_file'](macro_data)
            if actions is None:
                return False
            if not actions:
                callbacks['log'](f"⚠️ '{display_name}'에 실행할 동작이 없습니다.")
                return True

            for action in actions:
                pause_event.wait()
                if stop_event.is_set(): return False

                delay = action.get('delay', 0) / speed
                stop_event.wait(delay)

                if stop_event.is_set(): return False

                action_type = action['type']
                pos = action.get('pos')
                if pos: pyautogui.moveTo(pos, duration=0)

                if action_type == ActionType.MOUSE_DOWN.value: pyautogui.mouseDown(button=action['button'])
                elif action_type == ActionType.MOUSE_UP.value: pyautogui.mouseUp(button=action['button'])
                elif action_type == ActionType.KEY_DOWN.value: pyautogui.keyDown(action['key'])
                elif action_type == ActionType.KEY_UP.value: pyautogui.keyUp(action['key'])

        if stop_event.is_set(): return False

        try:
            item_delay = float(item_info.get('delay', 0))
            if item_delay > 0:
                callbacks['log'](f"🔗 다음 동작까지 {item_delay}초 대기...")
                stop_event.wait(timeout=item_delay)
        except (ValueError, TypeError):
            callbacks['log'](f"⚠️ 매크로 간 간격 값 '{item_info.get('delay')}'이(가) 잘못되었습니다.")

        return not stop_event.is_set()

# --- 1. 이미지 매크로 로직 클래스 ---
class AutoClickerMacro:
    def __init__(self, callbacks):
        self.c = callbacks
        self.is_running = False
        self.is_paused = False
        self.macro_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

    def start(self, settings):
        if self.is_running:
            self.c['log']("⚠️ 이미 이미지 매크로가 실행 중입니다.")
            return
        if not settings['image_folder']:
            self.c['log']("⚠️ 먼저 이미지 폴더를 선택해주세요.")
            return
        self.is_running = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()
        self.macro_thread = threading.Thread(target=self.run_macro, args=(settings,), daemon=True)
        self.macro_thread.start()
        self.c['update_ui'](running=True)

    def stop(self):
        if not self.is_running: return
        self.is_running = False
        self.stop_event.set()
        self.pause_event.set()
        self.c['log']("이미지 매크로 중지를 요청했습니다...")

    def pause_or_resume(self):
        if not self.is_running: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.clear()
            self.c['log']("⏸️ 이미지 매크로 일시정지.")
            self.c['update_status']("이미지 매크로 일시정지 중...")
        else:
            self.pause_event.set()
            self.c['log']("▶️ 이미지 매크로 재개.")
            self.c['update_status']("이미지 매크로 실행 중...")
        self.c['update_ui'](paused=self.is_paused)

    def run_macro(self, settings):
        self.c['log']("🚀 이미지 매크로를 시작합니다...")
        self.c['update_status']("이미지 매크로 실행 중...")
        start_time = time.time()
        loop_count = 0
        try:
            while self.is_running:
                if settings['repeat_mode'] == RepeatMode.COUNT and loop_count >= settings['repeat_value']:
                    self.c['log'](f"👍 {loop_count}회 반복 완료.")
                    break
                if settings['repeat_mode'] == RepeatMode.DURATION and (time.time() - start_time) / 60 >= settings['repeat_value']:
                    self.c['log'](f"👍 {settings['repeat_value']}분 실행 완료.")
                    break
                self.pause_event.wait()
                if not self.is_running: break
                execute_image_scan(self.c['log'], settings['image_folder'], self.stop_event, self.pause_event)
                if not self.is_running: break
                loop_count += 1
                self.c['log'](f"👍 순회 완료. {settings['repeat_delay']}초 후 다시 시작.")
                self.stop_event.wait(timeout=settings['repeat_delay'])
        except Exception as e:
            self.c['log'](f"🔥 매크로 실행 중 치명적 오류: {e}")
        finally:
            self.is_running = False
            self.is_paused = False
            self.c['update_ui'](running=False, paused=False)
            self.c['log']("🛑 이미지 매크로가 중지되었습니다.")
            self.c['update_status']("준비")

# --- 2. 녹화 매크로 로직 클래스 ---
class RecordingMacro:
    def __init__(self, callbacks):
        self.c = callbacks
        self.recorded_actions = []
        self.is_recording = False
        self.is_playing = False
        self.is_paused = False
        self.playback_thread = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.last_action_time = None
        self.is_mouse_down = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

    def start_recording(self):
        if self.is_recording:
            self.c['log']("⚠️ 이미 녹화가 진행 중입니다.")
            return
        self.is_recording = True
        self.is_mouse_down = False
        self.recorded_actions = []
        self.last_action_time = time.time()
        self.mouse_listener = mouse.Listener(on_click=self._on_click, on_move=self._on_move)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.mouse_listener.start()
        self.keyboard_listener.start()
        self.c['update_ui'](recording=True)
        self.c['log']("🔴 녹화를 시작합니다... (마우스와 키보드 입력 기록)")

    def stop_recording(self):
        if not self.is_recording: return
        if self.mouse_listener: self.mouse_listener.stop()
        if self.keyboard_listener: self.keyboard_listener.stop()
        self.is_recording = False
        self.c['update_ui'](recording=False)
        self.c['log'](f"⏹️ 녹화 중지. {len(self.recorded_actions)}개 동작 기록됨.")
        if self.recorded_actions:
            self.c['add_macro_to_list'](self.recorded_actions)
            self.recorded_actions = []

    def _get_key_str(self, key):
        if hasattr(key, 'char'): return key.char
        elif hasattr(key, 'name'): return key.name.lower()
        return None

    def _on_press(self, key):
        if not self.is_recording: return
        key_str = self._get_key_str(key)
        if key_str:
            current_time = time.time()
            delay = current_time - self.last_action_time
            self.last_action_time = current_time
            self.recorded_actions.append({'type': ActionType.KEY_DOWN.value, 'key': key_str, 'delay': delay})

    def _on_release(self, key):
        if not self.is_recording: return
        key_str = self._get_key_str(key)
        if key_str:
            current_time = time.time()
            delay = current_time - self.last_action_time
            self.last_action_time = current_time
            self.recorded_actions.append({'type': ActionType.KEY_UP.value, 'key': key_str, 'delay': delay})

    def _on_click(self, x, y, button, pressed):
        if not self.is_recording: return
        self.is_mouse_down = pressed
        current_time = time.time()
        delay = current_time - self.last_action_time
        self.last_action_time = current_time
        action_type = ActionType.MOUSE_DOWN.value if pressed else ActionType.MOUSE_UP.value
        self.recorded_actions.append({'type': action_type, 'pos': (x, y), 'button': str(button).replace('Button.', ''), 'delay': delay})

    def _on_move(self, x, y):
        if self.is_recording and self.is_mouse_down:
            current_time = time.time()
            delay = current_time - self.last_action_time
            self.last_action_time = current_time
            self.recorded_actions.append({'type': ActionType.MOVE.value, 'pos': (x, y), 'delay': delay})

    def start_playback(self, settings):
        if self.is_playing:
            self.c['log']("⚠️ 이미 재생 중입니다.")
            return
        if not settings['playlist']:
            self.c['log']("⚠️ 재생 목록이 비어있습니다.")
            return
        self.is_playing = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()
        self.playback_thread = threading.Thread(target=self.run_playback, args=(settings,), daemon=True)
        self.playback_thread.start()
        self.c['update_ui'](playing=True)

    def stop_playback(self):
        if not self.is_playing: return
        self.is_playing = False
        self.stop_event.set()
        self.pause_event.set()
        self.c['log']("재생 중지를 요청했습니다...")

    def pause_or_resume_playback(self):
        if not self.is_playing: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.clear()
            self.c['log']("⏸️ 매크로 체인 일시정지.")
            self.c['update_status']("매크로 체인 일시정지 중...")
        else:
            self.pause_event.set()
            self.c['log']("▶️ 매크로 체인 재개.")
            self.c['update_status']("매크로 체인 재생 중...")
        self.c['update_ui'](paused=self.is_paused)

    def run_playback(self, settings):
        self.c['log']("🚀 매크로 체인 재생을 시작합니다...")
        self.c['update_status']("녹화 매크로 재생 중...")
        pyautogui.PAUSE = 0
        start_time = time.time()
        loop_count = 0
        try:
            while self.is_playing:
                if settings['repeat_mode'] == RepeatMode.COUNT and loop_count >= settings['repeat_value']:
                    self.c['log'](f"👍 {loop_count}회 반복 완료.")
                    break
                if settings['repeat_mode'] == RepeatMode.DURATION and (time.time() - start_time) / 60 >= settings['repeat_value']:
                    self.c['log'](f"👍 {settings['repeat_value']}분 실행 완료.")
                    break
                for item_info in settings['playlist']:
                    if not self.is_playing: break
                    if not MacroExecutor.execute_macro_item(item_info, self.c, self.stop_event, self.pause_event, settings['playback_speed'], settings['image_timeout'], settings.get('app'), settings.get('tree')):
                        self.is_playing = False
                        break
                if not self.is_playing: break
                loop_count += 1
                self.c['log'](f"👍 재생 목록 완료. {settings['repeat_delay']}초 후 반복.")
                self.stop_event.wait(timeout=settings['repeat_delay'])
        except Exception as e:
            self.c['log'](f"🔥 재생 중 오류: {e}")
        finally:
            self.is_playing = False
            self.is_paused = False
            self.c['update_ui'](playing=False, paused=False)
            self.c['log']("🛑 매크로 재생이 중지되었습니다.")
            self.c['update_status']("준비")

    def test_run_single_item(self, settings):
        if self.is_playing:
            self.c['log']("⚠️ 다른 매크로가 이미 재생 중입니다.")
            return
        self.is_playing = True
        self.stop_event.clear()
        self.pause_event.set()
        self.playback_thread = threading.Thread(target=self._run_single, args=(settings,), daemon=True)
        self.playback_thread.start()
        self.c['update_ui'](playing=True)

    def _run_single(self, settings):
        self.c['log'](f"🧪 '{settings['playlist'][0]['display_name']}' 항목 테스트 시작...")
        try:
            MacroExecutor.execute_macro_item(settings['playlist'][0], self.c, self.stop_event, self.pause_event, settings['playback_speed'], settings['image_timeout'], settings.get('app'), settings.get('tree'))
        except Exception as e:
            self.c['log'](f"🔥 테스트 실행 중 오류: {e}")
        finally:
            self.is_playing = False
            self.c['update_ui'](playing=False)
            self.c['log']("🧪 테스트 실행 완료.")
            self.c['update_status']("준비")


# --- 3. 매크로 그룹 로직 클래스 ---
class ChainGroupMacro:
    def __init__(self, callbacks):
        self.c = callbacks
        self.is_playing = False
        self.is_paused = False
        self.playback_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

    def start_playback(self, settings):
        if self.is_playing:
            self.c['log']("⚠️ 이미 그룹 재생 중입니다.")
            return
        if not settings['chain_playlist']:
            self.c['log']("⚠️ 그룹 재생 목록이 비어있습니다.")
            return
        self.is_playing = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()
        self.playback_thread = threading.Thread(target=self.run_playback, args=(settings,), daemon=True)
        self.playback_thread.start()
        self.c['update_ui'](playing=True)

    def stop_playback(self):
        if not self.is_playing: return
        self.is_playing = False
        self.stop_event.set()
        self.pause_event.set()
        self.c['log']("그룹 재생 중지를 요청했습니다...")

    def pause_or_resume_playback(self):
        if not self.is_playing: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.clear()
            self.c['log']("⏸️ 매크로 그룹 일시정지.")
            self.c['update_status']("매크로 그룹 일시정지 중...")
        else:
            self.pause_event.set()
            self.c['log']("▶️ 매크로 그룹 재개.")
            self.c['update_status']("매크로 그룹 재생 중...")
        self.c['update_ui'](paused=self.is_paused)

    def run_playback(self, settings):
        self.c['log']("🚀 매크로 그룹 재생을 시작합니다...")
        self.c['update_status']("매크로 그룹 재생 중...")
        pyautogui.PAUSE = 0
        start_time = time.time()
        loop_count = 0
        try:
            while self.is_playing:
                if settings['repeat_mode'] == RepeatMode.COUNT and loop_count >= settings['repeat_value']:
                    self.c['log'](f"👍 그룹 {loop_count}회 반복 완료.")
                    break
                if settings['repeat_mode'] == RepeatMode.DURATION and (time.time() - start_time) / 60 >= settings['repeat_value']:
                    self.c['log'](f"👍 그룹 {settings['repeat_value']}분 실행 완료.")
                    break
                for chain_index, chain_info in enumerate(settings['chain_playlist']):
                    if not self.is_playing: break
                    self.pause_event.wait()
                    chain_path = chain_info['path']
                    chain_repeats = chain_info['repeats']
                    chain_delay = chain_info['delay_after']
                    self.c['log'](f"---  그룹 ({chain_index+1}/{len(settings['chain_playlist'])}) '{os.path.basename(chain_path)}' (x{chain_repeats}) 실행 ---")
                    macro_playlist = self.c['load_macros_from_chain'](chain_path)
                    if macro_playlist is None:
                        self.is_playing = False
                        break
                    for i in range(chain_repeats):
                        if not self.is_playing: break
                        self.pause_event.wait()
                        self.c['log'](f"➡️ '{os.path.basename(chain_path)}' {i+1}/{chain_repeats}번째 반복 시작")
                        for macro_item in macro_playlist:
                            if not MacroExecutor.execute_macro_item(macro_item, self.c, self.stop_event, self.pause_event, settings['playback_speed'], settings['image_timeout'], settings.get('app'), settings.get('tree')):
                                self.is_playing = False
                                break
                            if not self.is_playing: break
                    if self.is_playing and chain_delay > 0:
                        self.c['log'](f"⏰ 다음 체인까지 {chain_delay}초 대기...")
                        self.stop_event.wait(timeout=chain_delay)
                if not self.is_playing: break
                loop_count += 1
                self.c['log'](f"👍 그룹 전체 1회 실행 완료. {settings['repeat_delay']}초 후 그룹 반복.")
                self.stop_event.wait(timeout=settings['repeat_delay'])
        except Exception as e:
            self.c['log'](f"🔥 그룹 재생 중 오류: {e}")
        finally:
            self.is_playing = False
            self.is_paused = False
            self.c['update_ui'](playing=False, paused=False)
            self.c['log']("🛑 매크로 그룹 재생이 중지되었습니다.")
            self.c['update_status']("준비")

# --- 4. 각 탭의 GUI를 구성하는 클래스 ---
class ImageMacroTab(ttk.Frame):
    def __init__(self, parent, app, config=None):
        super().__init__(parent)
        self.app = app
        callbacks = {
            'log': self.log,
            'update_ui': self.update_ui_state,
            'update_status': self.app.update_status
        }
        self.macro = AutoClickerMacro(callbacks)
        self.area_selector = None
        self._create_widgets()
        if config:
            last_folder = config.get('last_folder')
            if last_folder and os.path.isdir(last_folder):
                self.image_folder_path.set(last_folder)
                self.load_settings()

    def log(self, message):
        self.app.log(f"[이미지] {message}")

    def _create_widgets(self):
        settings_frame = ttk.LabelFrame(self, text="이미지 매크로 설정")
        settings_frame.pack(fill=tk.X, padx=10, pady=5, anchor=tk.N)
        self.image_folder_path = tk.StringVar()
        self.interval_var = tk.StringVar(value="0.1")
        self.confidence_var = tk.StringVar(value="0.7")
        self.frenzy_mode_var = tk.BooleanVar(value=False)
        self.use_search_area_var = tk.BooleanVar(value=False)
        self.search_area_display_var = tk.StringVar(value="미설정")
        self.search_area_coords = None
        r = 0
        ttk.Label(settings_frame, text="이미지 폴더:").grid(row=r, column=0, sticky=tk.W, padx=5, pady=2)
        self.folder_entry = ttk.Entry(settings_frame, textvariable=self.image_folder_path, state='readonly')
        self.folder_entry.grid(row=r, column=1, sticky=tk.EW, padx=5, pady=2)
        self.folder_button = ttk.Button(settings_frame, text="폴더 선택", command=self.select_folder)
        self.folder_button.grid(row=r, column=2, padx=5, pady=2)
        r += 1
        ttk.Label(settings_frame, text="클릭 간격(초):").grid(row=r, column=0, sticky=tk.W, padx=5, pady=2)
        self.interval_entry = ttk.Entry(settings_frame, textvariable=self.interval_var, width=12)
        self.interval_entry.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        r += 1
        ttk.Label(settings_frame, text="인식 정확도(0.1~1.0):").grid(row=r, column=0, sticky=tk.W, padx=5, pady=2)
        self.confidence_entry = ttk.Entry(settings_frame, textvariable=self.confidence_var, width=12)
        self.confidence_entry.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        r += 1
        ttk.Label(settings_frame, text="3회 클릭 모드:").grid(row=r, column=0, sticky=tk.W, padx=5, pady=2)
        self.frenzy_mode_check = ttk.Checkbutton(settings_frame, text="활성화", variable=self.frenzy_mode_var)
        self.frenzy_mode_check.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        r += 1
        ttk.Label(settings_frame, text="검색 영역:").grid(row=r, column=0, sticky=tk.W, padx=5, pady=2)
        self.use_search_area_check = ttk.Checkbutton(settings_frame, text="활성화", variable=self.use_search_area_var)
        self.use_search_area_check.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        self.set_area_button = ttk.Button(settings_frame, text="영역 설정 (F9)", command=self.start_defining_area)
        self.set_area_button.grid(row=r, column=2, padx=5, pady=2)
        r += 1
        ttk.Label(settings_frame, textvariable=self.search_area_display_var, foreground="blue").grid(row=r, column=1, columnspan=2, sticky=tk.W, padx=5, pady=2)
        settings_frame.columnconfigure(1, weight=1)
        self.repeat_frame = ttk.LabelFrame(self, text="반복 설정")
        self.repeat_frame.pack(fill=tk.X, padx=10, pady=5)
        self.repeat_mode_var = tk.StringVar(value=RepeatMode.INFINITE.name)
        self.repeat_value_var = tk.StringVar(value="10")
        self.repeat_delay_var = tk.StringVar(value="1.0")
        repeat_mode_frame = ttk.Frame(self.repeat_frame)
        repeat_mode_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        ttk.Radiobutton(repeat_mode_frame, text="무한 반복", variable=self.repeat_mode_var, value=RepeatMode.INFINITE.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(repeat_mode_frame, text="횟수 반복:", variable=self.repeat_mode_var, value=RepeatMode.COUNT.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_count_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_value_var, width=8)
        self.repeat_count_entry.pack(side=tk.LEFT, padx=(2, 10))
        ttk.Radiobutton(repeat_mode_frame, text="시간(분) 반복:", variable=self.repeat_mode_var, value=RepeatMode.DURATION.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_duration_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_value_var, width=8)
        self.repeat_duration_entry.pack(side=tk.LEFT, padx=2)
        repeat_delay_frame = ttk.Frame(self.repeat_frame)
        repeat_delay_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        ttk.Label(repeat_delay_frame, text="각 순회 후 대기(초):").pack(side=tk.LEFT)
        ttk.Entry(repeat_delay_frame, textvariable=self.repeat_delay_var, width=8).pack(side=tk.LEFT, padx=2)
        self.toggle_repeat_entry()
        control_frame = ttk.LabelFrame(self, text="제어")
        control_frame.pack(fill=tk.BOTH, padx=10, pady=5, expand=True)
        control_frame.columnconfigure((0,1,2), weight=1)
        self.start_button = ttk.Button(control_frame, text="시작 (F3)", command=self.start_macro)
        self.start_button.grid(row=0, column=0, sticky=tk.EW, padx=5, pady=5)
        self.pause_button = ttk.Button(control_frame, text="일시정지 (F5)", command=self.macro.pause_or_resume, state=tk.DISABLED)
        self.pause_button.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.stop_button = ttk.Button(control_frame, text="중지 (F4)", command=self.macro.stop, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=2, sticky=tk.EW, padx=5, pady=5)

    def toggle_repeat_entry(self):
        try:
            if not self.repeat_frame.winfo_exists(): return
            mode = self.repeat_mode_var.get()
            self.repeat_count_entry.config(state=tk.NORMAL if mode == RepeatMode.COUNT.name else tk.DISABLED)
            self.repeat_duration_entry.config(state=tk.NORMAL if mode == RepeatMode.DURATION.name else tk.DISABLED)
        except tk.TclError: pass

    def start_macro(self):
        self.save_settings()
        try:
            settings = {
                'image_folder': self.image_folder_path.get(),
                'repeat_mode': RepeatMode[self.repeat_mode_var.get()],
                'repeat_value': int(self.repeat_value_var.get()),
                'repeat_delay': float(self.repeat_delay_var.get())
            }
            self.macro.start(settings)
        except (ValueError, TypeError):
            self.log("⚠️ 반복 횟수/시간 또는 대기 시간 값이 올바르지 않습니다.")
        except Exception as e:
            self.log(f"🔥 시작 오류: {e}")

    def start_defining_area(self):
        if self.area_selector and self.area_selector.is_alive():
            self.log("⚠️ 이미 영역 설정이 진행 중입니다.")
            return
        self.log("영역의 시작점을 클릭하고, 끝점을 다시 클릭하세요. (ESC: 취소)")
        self.app.update_status("화면 영역 설정 중...")
        self.area_selector = GlobalAreaSelector(self)

    def set_area(self, x, y, w, h):
        self.search_area_coords = (x, y, w, h)
        self.search_area_display_var.set(f"설정됨: X={x}, Y={y}, W={w}, H={h}")
        self.log(f"✅ 검색 영역이 설정되었습니다: {self.search_area_coords}")
        self.app.update_status("준비")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.image_folder_path.set(folder)
            self.app.log_event(f"📂 폴더 선택됨: {os.path.basename(folder)}")
            self.load_settings()

    def load_settings(self):
        path = os.path.join(self.image_folder_path.get(), 'config.json')
        if not os.path.exists(path): return
        try:
            with open(path, 'r', encoding='utf-8') as f: s = json.load(f)
            self.interval_var.set(s.get('click_interval', '0.1'))
            self.confidence_var.set(s.get('confidence_level', '0.7'))
            self.frenzy_mode_var.set(s.get('frenzy_mode', False))
            self.use_search_area_var.set(s.get('use_search_area', False))
            coords = s.get('search_area_coords')
            if coords and isinstance(coords, list) and len(coords) == 4:
                self.search_area_coords = tuple(coords)
                self.search_area_display_var.set(f"설정됨: X={coords[0]}, Y={coords[1]}, W={coords[2]}, H={coords[3]}")
            else:
                self.search_area_coords = None
                self.search_area_display_var.set("미설정")
            self.log("저장된 설정을 불러왔습니다.")
        except Exception as e:
            self.app.log_event(f"⚠️ 설정 로드 실패: {e}")

    def save_settings(self):
        if not self.image_folder_path.get(): return
        s = {
            'click_interval': self.interval_var.get(),
            'confidence_level': self.confidence_var.get(),
            'frenzy_mode': self.frenzy_mode_var.get(),
            'use_search_area': self.use_search_area_var.get(),
            'search_area_coords': self.search_area_coords
        }
        path = os.path.join(self.image_folder_path.get(), 'config.json')
        try:
            with open(path, 'w', encoding='utf-8') as f: json.dump(s, f, indent=4)
            self.app.log_event(f"💾 현재 설정을 폴더에 저장했습니다.")
        except Exception as e:
            self.app.log_event(f"⚠️ 설정 저장 실패: {e}")

    def update_ui_state(self, running=None, paused=None):
        try:
            if running is not None:
                is_running = running
                state = tk.DISABLED if is_running else tk.NORMAL
                self.start_button.config(state=state)
                self.stop_button.config(state=tk.NORMAL if is_running else tk.DISABLED)
                self.pause_button.config(state=tk.NORMAL if is_running else tk.DISABLED)
                for widget in [self.folder_button, self.confidence_entry, self.frenzy_mode_check, self.use_search_area_check, self.set_area_button, self.interval_entry]:
                    widget.config(state=state)
                if self.repeat_frame.winfo_exists():
                    for child in self.repeat_frame.winfo_children():
                        child.config(state=state)
                self.toggle_repeat_entry()
            if paused is not None:
                self.pause_button.config(text="재개 (F5)" if paused else "일시정지 (F5)")
        except tk.TclError: pass

class RecordingMacroTab(ttk.Frame):
    def __init__(self, parent, app, config=None):
        super().__init__(parent)
        self.app = app
        callbacks = {
            'log': self.log,
            'update_ui': self.update_ui_state,
            'update_status': self.app.update_status,
            'add_macro_to_list': self.add_memory_macro_to_list,
            'load_actions_from_file': self.load_actions_from_file
        }
        self.macro = RecordingMacro(callbacks)
        self.new_recording_counter = 1
        self.playlist_data = {}
        self.current_chain_path = None
        self.is_dirty = False
        self._create_widgets()
        if config:
            last_chain = config.get('last_chain')
            if last_chain and os.path.isfile(last_chain):
                self.load_chain(path=last_chain)

    def _set_dirty(self, dirty=True):
        if self.is_dirty == dirty: return
        self.is_dirty = dirty
        title = "푸크로 V4.2"
        if dirty: title += "*"
        self.app.root.title(title)

    def log(self, message):
        self.app.log(f"[체인] {message}")

    def _create_widgets(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=(10,5))
        top_frame.columnconfigure((0, 1), weight=1)
        record_frame = ttk.LabelFrame(top_frame, text="녹화")
        record_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0,5))
        record_frame.columnconfigure(0, weight=1)
        self.record_start_button = ttk.Button(record_frame, text="녹화 시작 (F1)", command=self.macro.start_recording)
        self.record_start_button.pack(fill=tk.X, padx=5, pady=5)
        self.record_stop_button = ttk.Button(record_frame, text="녹화 중지 (F2)", command=self.macro.stop_recording, state=tk.DISABLED)
        self.record_stop_button.pack(fill=tk.X, padx=5, pady=5)
        play_frame = ttk.LabelFrame(top_frame, text="재생 (현재 체인)")
        play_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(5,0))
        play_frame.columnconfigure(0, weight=1)
        self.play_start_button = ttk.Button(play_frame, text="재생 시작 (F3)", command=self.start_macro_chain)
        self.play_start_button.pack(fill=tk.X, padx=5, pady=5)
        self.pause_play_button = ttk.Button(play_frame, text="일시정지 (F5)", command=self.macro.pause_or_resume_playback, state=tk.DISABLED)
        self.pause_play_button.pack(fill=tk.X, padx=5, pady=5)
        self.play_stop_button = ttk.Button(play_frame, text="재생 중지 (F4)", command=self.macro.stop_playback, state=tk.DISABLED)
        self.play_stop_button.pack(fill=tk.X, padx=5, pady=5)
        chain_io_frame = ttk.LabelFrame(top_frame, text="체인 파일")
        chain_io_frame.grid(row=0, column=2, sticky=tk.NSEW, padx=(5,0))
        self.load_chain_button = ttk.Button(chain_io_frame, text="불러오기", command=self.load_chain)
        self.load_chain_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_chain_button = ttk.Button(chain_io_frame, text="저장", command=self.save_chain)
        self.save_chain_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_as_chain_button = ttk.Button(chain_io_frame, text="다른 이름으로...", command=lambda: self.save_chain(save_as=True))
        self.save_as_chain_button.pack(fill=tk.X, padx=5, pady=5)
        playlist_frame = ttk.LabelFrame(self, text="매크로 체인 편집기 (재생 목록)")
        playlist_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        playlist_frame.columnconfigure(0, weight=1)
        playlist_frame.rowconfigure(0, weight=1)
        list_container = ttk.Frame(playlist_frame)
        list_container.grid(row=0, column=0, sticky='nsew', pady=5, padx=5)
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        columns = ("#1", "#2")
        # ✨ [다중 선택 기능] selectmode를 'extended'로 변경
        self.macro_tree = ttk.Treeview(list_container, columns=columns, show="headings", selectmode="extended")
        self.macro_tree.heading("#1", text="매크로")
        self.macro_tree.heading("#2", text="실행 후 대기(초)")
        self.macro_tree.column("#1", width=230)
        self.macro_tree.column("#2", width=90, anchor='center')
        self.macro_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.macro_tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.macro_tree['yscrollcommand'] = scrollbar.set
        self.macro_tree.bind("<Double-1>", self.on_tree_double_click)
        self.macro_tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        btn_frame = ttk.Frame(playlist_frame)
        btn_frame.grid(row=0, column=1, sticky='ns', padx=(0, 5), pady=5)
        add_btn_frame = ttk.LabelFrame(btn_frame, text="추가")
        add_btn_frame.pack(pady=2, fill=tk.X)
        self.add_file_button = ttk.Button(add_btn_frame, text="녹화 파일", command=self.add_file_macro_to_list)
        self.add_file_button.pack(fill=tk.X, padx=2, pady=(2,0))
        self.add_wait_image_button = ttk.Button(add_btn_frame, text="이미지 대기", command=self.add_wait_image_macro_to_list)
        self.add_wait_image_button.pack(fill=tk.X, padx=2, pady=2)
        edit_btn_frame = ttk.LabelFrame(btn_frame, text="편집")
        edit_btn_frame.pack(pady=(10,2), fill=tk.X)
        self.remove_button = ttk.Button(edit_btn_frame, text="제거", command=self.remove_selected_macro)
        self.remove_button.pack(fill=tk.X, padx=2, pady=2)
        self.up_button = ttk.Button(edit_btn_frame, text="▲", command=self.move_macro_up)
        self.up_button.pack(fill=tk.X, padx=2, pady=2)
        self.down_button = ttk.Button(edit_btn_frame, text="▼", command=self.move_macro_down)
        self.down_button.pack(fill=tk.X, padx=2, pady=2)
        self.clear_button = ttk.Button(edit_btn_frame, text="모두 삭제", command=self.clear_macro_list)
        self.clear_button.pack(fill=tk.X, padx=2, pady=2)
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)
        self.save_button = ttk.Button(bottom_frame, text="선택 항목 저장", command=self.save_selected_macro, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=(0, 10))
        self.test_run_button = ttk.Button(bottom_frame, text="선택 항목 테스트", command=self.test_run_selected, state=tk.DISABLED)
        self.test_run_button.pack(side=tk.LEFT)
        self.play_settings_frame = ttk.LabelFrame(self, text="재생 설정 (현재 체인)")
        self.play_settings_frame.pack(fill=tk.X, padx=10, pady=5)
        self.repeat_mode_var = tk.StringVar(value=RepeatMode.INFINITE.name)
        self.repeat_value_var = tk.StringVar(value="10")
        self.repeat_delay_var = tk.StringVar(value="1.0")
        self.playback_speed_var = tk.StringVar(value="1.0x")
        self.image_timeout_var = tk.StringVar(value="30")
        repeat_mode_frame = ttk.Frame(self.play_settings_frame)
        repeat_mode_frame.grid(row=0, column=0, columnspan=4, sticky='w', padx=5, pady=(5,0))
        ttk.Radiobutton(repeat_mode_frame, text="무한 반복", variable=self.repeat_mode_var, value=RepeatMode.INFINITE.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(repeat_mode_frame, text="횟수:", variable=self.repeat_mode_var, value=RepeatMode.COUNT.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_count_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_value_var, width=8)
        self.repeat_count_entry.pack(side=tk.LEFT, padx=(2, 10))
        ttk.Radiobutton(repeat_mode_frame, text="시간(분):", variable=self.repeat_mode_var, value=RepeatMode.DURATION.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_duration_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_value_var, width=8)
        self.repeat_duration_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(self.play_settings_frame, text="전체 반복 대기(초):").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(self.play_settings_frame, textvariable=self.repeat_delay_var, width=8).grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(self.play_settings_frame, text="재생 속도:").grid(row=1, column=2, sticky='w', padx=15, pady=2)
        self.speed_combo = ttk.Combobox(self.play_settings_frame, textvariable=self.playback_speed_var, values=["0.5x", "1.0x", "1.5x", "2.0x", "5.0x"], width=6)
        self.speed_combo.grid(row=1, column=3, sticky='w', pady=2)
        img_wait_frame = ttk.Frame(self.play_settings_frame)
        img_wait_frame.grid(row=2, column=0, columnspan=2, sticky='w', padx=5, pady=(2,5))
        ttk.Label(img_wait_frame, text="이미지 대기(초):").pack(side=tk.LEFT)
        help_button = ttk.Button(img_wait_frame, text="?", width=2, command=self.show_help)
        help_button.pack(side=tk.LEFT, padx=2)
        ttk.Entry(self.play_settings_frame, textvariable=self.image_timeout_var, width=8).grid(row=2, column=1, sticky='w', pady=(2,5))
        self.toggle_repeat_entry()

    def show_help(self):
        self.app.notebook.select(4)

    def toggle_repeat_entry(self):
        try:
            if not self.play_settings_frame.winfo_exists(): return
            mode = self.repeat_mode_var.get()
            self.repeat_count_entry.config(state=tk.NORMAL if mode == RepeatMode.COUNT.name else tk.DISABLED)
            self.repeat_duration_entry.config(state=tk.NORMAL if mode == RepeatMode.DURATION.name else tk.DISABLED)
        except tk.TclError: pass

    def start_macro_chain(self):
        playlist = []
        for item_id in self.macro_tree.get_children():
            item_data = self.playlist_data.get(item_id)
            if item_data:
                item_info = item_data.copy()
                item_info['item_id'] = item_id
                item_info['delay'] = self.macro_tree.set(item_id, "#2")
                item_info['display_name'] = self.macro_tree.set(item_id, "#1")
                playlist.append(item_info)
        if not playlist:
            self.log("⚠️ 재생 목록에 매크로를 추가해주세요.")
            return
        try:
            speed_str = self.playback_speed_var.get().replace('x', '')
            settings = {
                'playlist': playlist,
                'repeat_mode': RepeatMode[self.repeat_mode_var.get()],
                'repeat_value': int(self.repeat_value_var.get()),
                'repeat_delay': float(self.repeat_delay_var.get()),
                'playback_speed': float(speed_str),
                'image_timeout': int(self.image_timeout_var.get()),
                'app': self.app,
                'tree': self.macro_tree
            }
            self.macro.start_playback(settings)
        except (ValueError, TypeError):
            self.log("⚠️ 재생 설정 값이 올바르지 않습니다. (숫자 확인)")
        except Exception as e:
            self.log(f"🔥 재생 시작 오류: {e}")

    def test_run_selected(self):
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.log("⚠️ 테스트할 항목을 목록에서 선택하세요.")
            return
        item_id = selected_items[0]
        item_data = self.playlist_data.get(item_id)
        if not item_data: return

        item_info = item_data.copy()
        item_info['item_id'] = item_id
        item_info['delay'] = self.macro_tree.set(item_id, "#2")
        item_info['display_name'] = self.macro_tree.set(item_id, "#1")

        try:
            speed_str = self.playback_speed_var.get().replace('x', '')
            settings = {
                'playlist': [item_info],
                'playback_speed': float(speed_str),
                'image_timeout': int(self.image_timeout_var.get()),
                'app': self.app,
                'tree': self.macro_tree
            }
            self.macro.test_run_single_item(settings)
        except (ValueError, TypeError):
            self.log("⚠️ 재생 설정 값이 올바르지 않습니다. (숫자 확인)")
        except Exception as e:
            self.log(f"🔥 테스트 시작 오류: {e}")


    def add_file_macro_to_list(self):
        files = filedialog.askopenfilenames(title="녹화 파일 추가", filetypes=[("JSON files", "*.json")])
        if files:
            for file_path in files:
                display_name = os.path.basename(file_path)
                item_id = self.macro_tree.insert("", tk.END, values=(display_name, "1.0"))
                self.playlist_data[item_id] = {'type': MacroType.FILE.value, 'data': file_path, 'display_name': display_name}
            self.log(f"✅ {len(files)}개 녹화 매크로를 추가했습니다.")
            self._set_dirty()

    def add_wait_image_macro_to_list(self):
        file = filedialog.askopenfilename(title="이미지(대기) 파일 선택", filetypes=[("PNG files", "*.png")])
        if file:
            display_name = f"[이미지 대기] {os.path.basename(file)}"
            item_id = self.macro_tree.insert("", tk.END, values=(display_name, "1.0"), tags=('image_wait_macro',))
            self.macro_tree.tag_configure('image_wait_macro', foreground='#E69138')
            self.playlist_data[item_id] = {'type': MacroType.IMAGE_WAIT.value, 'data': file, 'display_name': display_name}
            self.log(f"✅ 이미지(대기) '{os.path.basename(file)}'를 추가했습니다.")
            self._set_dirty()

    def add_memory_macro_to_list(self, actions):
        display_name = f"새 녹화 {self.new_recording_counter}"
        self.new_recording_counter += 1
        item_id = self.macro_tree.insert("", tk.END, values=(display_name, "1.0"), tags=('memory_macro',))
        self.macro_tree.tag_configure('memory_macro', foreground='blue')
        self.playlist_data[item_id] = {'type': MacroType.MEMORY.value, 'data': actions, 'display_name': display_name}
        self.log(f"✅ '{display_name}'를 재생 목록에 추가했습니다.")
        self._set_dirty()

    def save_chain(self, save_as=False):
        if not self.playlist_data:
            self.log("⚠️ 저장할 체인이 없습니다.")
            return False
        file_path = self.current_chain_path
        if save_as or not file_path:
            file_path = filedialog.asksaveasfilename(title="매크로 체인 저장", defaultextension=".pchain", filetypes=[("Pucro Chain files", "*.pchain"), ("All files", "*.*")])
        if not file_path: return False
        self.current_chain_path = file_path
        chain_content = {'settings': {'repeat_mode': self.repeat_mode_var.get(), 'repeat_value': self.repeat_value_var.get(), 'repeat_delay': self.repeat_delay_var.get(), 'playback_speed': self.playback_speed_var.get(), 'image_timeout': self.image_timeout_var.get()}, 'playlist': []}
        chain_dir = os.path.dirname(file_path)
        for item_id in self.macro_tree.get_children():
            item_data = self.playlist_data.get(item_id)
            if not item_data: continue
            data_path = item_data['data']
            if item_data['type'] in [MacroType.FILE.value, MacroType.IMAGE_WAIT.value]:
                try: data_path = os.path.relpath(data_path, chain_dir)
                except ValueError: pass
            chain_item = {'type': item_data['type'], 'data': data_path if item_data['type'] != MacroType.MEMORY.value else item_data['data'], 'display_name': self.macro_tree.set(item_id, "#1"), 'delay': self.macro_tree.set(item_id, "#2")}
            chain_content['playlist'].append(chain_item)
        try:
            with open(file_path, 'w', encoding='utf-8') as f: json.dump(chain_content, f, indent=4, ensure_ascii=False)
            self.app.log_event(f"💾 체인 저장 완료: '{os.path.basename(file_path)}'")
            self._set_dirty(False)
            return True
        except Exception as e:
            self.app.log_event(f"🔥 체인 저장 실패: {e}")
            return False

    def load_chain(self, path=None):
        if self.is_dirty:
            response = messagebox.askyesnocancel("확인", "저장되지 않은 변경사항이 있습니다. 계속 진행하시겠습니까?")
            if not response: return
        file_path = path
        if not file_path:
            file_path = filedialog.askopenfilename(title="매크로 체인 불러오기", filetypes=[("Pucro Chain files", "*.pchain"), ("All files", "*.*")])
        if not file_path: return
        self.current_chain_path = file_path
        try:
            with open(file_path, 'r', encoding='utf-8') as f: chain_content = json.load(f)
            self.clear_macro_list(from_load=True)
            settings = chain_content.get('settings', {})
            self.repeat_mode_var.set(settings.get('repeat_mode', RepeatMode.INFINITE.name))
            self.repeat_value_var.set(settings.get('repeat_value', '10'))
            self.repeat_delay_var.set(settings.get('repeat_delay', '1.0'))
            self.playback_speed_var.set(settings.get('playback_speed', '1.0x'))
            self.image_timeout_var.set(settings.get('image_timeout', '30'))
            self.toggle_repeat_entry()
            chain_dir = os.path.dirname(file_path)
            for item in chain_content.get('playlist', []):
                item_type = item.get('type')
                item_data = item.get('data')
                if item_type in [MacroType.FILE.value, MacroType.IMAGE_WAIT.value] and not os.path.isabs(item_data):
                    item_data = os.path.join(chain_dir, item_data)
                tags = ()
                if item_type == MacroType.MEMORY.value: tags = ('memory_macro',)
                elif item_type == MacroType.IMAGE_WAIT.value: tags = ('image_wait_macro',)
                item_id = self.macro_tree.insert("", tk.END, values=(item.get('display_name'), item.get('delay', '1.0')), tags=tags)
                self.playlist_data[item_id] = {'type': item_type, 'data': item_data, 'display_name': item.get('display_name')}
            self.macro_tree.tag_configure('memory_macro', foreground='blue')
            self.macro_tree.tag_configure('image_wait_macro', foreground='#E69138')
            self.app.log_event(f"💾 체인 불러오기 완료: '{os.path.basename(file_path)}'")
            self._set_dirty(False)
        except Exception as e:
            self.app.log_event(f"🔥 체인 불러오기 실패: {e}")
            messagebox.showerror("오류", f"체인 파일을 불러오는 중 오류가 발생했습니다.\n{e}")

    def load_actions_from_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
            return data.get('actions', [])
        except FileNotFoundError:
            self.log(f"🔥 파일 없음: '{os.path.basename(file_path)}'. 새 위치를 지정해주세요.")
            new_path = filedialog.askopenfilename(title=f"'{os.path.basename(file_path)}' 찾기", filetypes=[("JSON files", "*.json")])
            if new_path:
                for item_id, item_info in self.playlist_data.items():
                    if item_info.get('data') == file_path:
                        item_info['data'] = new_path
                        self.macro_tree.set(item_id, "#1", os.path.basename(new_path))
                        self._set_dirty()
                        break
                return self.load_actions_from_file(new_path)
            return None
        except Exception as e:
            self.log(f"🔥 '{os.path.basename(file_path)}' 파일 로드 실패: {e}")
            return None

    def update_ui_state(self, recording=None, playing=None, paused=None):
        try:
            is_busy = self.macro.is_playing or self.macro.is_recording
            if recording is not None:
                state = tk.DISABLED if recording else tk.NORMAL
                self.record_start_button.config(state=state)
                self.record_stop_button.config(state=tk.NORMAL if recording else tk.DISABLED)
            if playing is not None:
                state = tk.DISABLED if playing else tk.NORMAL
                self.play_start_button.config(state=state)
                self.play_stop_button.config(state=tk.NORMAL if playing else tk.DISABLED)
                self.pause_play_button.config(state=tk.NORMAL if playing else tk.DISABLED)
                for btn in [self.add_file_button, self.add_wait_image_button, self.remove_button, self.up_button, self.down_button, self.clear_button, self.save_chain_button, self.load_chain_button, self.save_as_chain_button, self.test_run_button]:
                    if btn.winfo_exists(): btn.config(state=state)
                if self.play_settings_frame.winfo_exists():
                    for child in self.play_settings_frame.winfo_children():
                        child.config(state=state)
                self.toggle_repeat_entry()
            if paused is not None and self.macro.is_playing:
                self.pause_play_button.config(text="재개 (F5)" if paused else "일시정지 (F5)")
            if self.macro.is_recording: self.app.update_status("녹화 중...")
            elif not is_busy: self.app.update_status("준비")
            self.on_tree_select(None)
        except tk.TclError: pass

    def on_tree_select(self, event):
        if self.macro.is_playing or self.macro.is_recording:
            self.save_button.config(state=tk.DISABLED)
            self.test_run_button.config(state=tk.DISABLED)
            return
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.save_button.config(state=tk.DISABLED)
            self.test_run_button.config(state=tk.DISABLED)
            return

        # 한 개만 선택되었을 때만 저장 및 테스트 버튼 활성화
        if len(selected_items) == 1:
            self.test_run_button.config(state=tk.NORMAL)
            item_id = selected_items[0]
            item_data = self.playlist_data.get(item_id)
            if item_data and item_data['type'] == MacroType.MEMORY.value:
                self.save_button.config(state=tk.NORMAL)
            else:
                self.save_button.config(state=tk.DISABLED)
        else: # 여러 개 선택 시 비활성화
            self.save_button.config(state=tk.DISABLED)
            self.test_run_button.config(state=tk.DISABLED)


    def on_tree_double_click(self, event):
        if self.macro.is_playing or self.macro.is_recording: return
        region = self.macro_tree.identify("region", event.x, event.y)
        if region != "cell": return
        column = self.macro_tree.identify_column(event.x)
        selected_item = self.macro_tree.focus()
        if not selected_item: return
        item_data = self.playlist_data.get(selected_item)
        if not item_data: return
        if column == "#2": self.edit_tree_cell(selected_item, column)
        elif column == "#1" and item_data['type'] != MacroType.FILE.value: self.edit_tree_cell(selected_item, column)

    def edit_tree_cell(self, item, column):
        column_box = self.macro_tree.bbox(item, column)
        entry_edit = ttk.Entry(self.macro_tree, justify='center')
        current_value = self.macro_tree.set(item, column)
        entry_edit.insert(0, current_value)
        entry_edit.select_range(0, tk.END)
        entry_edit.focus()
        entry_edit.place(x=column_box[0], y=column_box[1], w=column_box[2], h=column_box[3])
        def on_enter_pressed(event):
            new_value = entry_edit.get()
            self.macro_tree.set(item, column, new_value)
            if column == "#1": self.playlist_data[item]['display_name'] = new_value
            entry_edit.destroy()
            self._set_dirty()
        entry_edit.bind("<FocusOut>", lambda e: entry_edit.destroy())
        entry_edit.bind("<Return>", on_enter_pressed)

    def save_selected_macro(self):
        selected_items = self.macro_tree.selection()
        if not selected_items or len(selected_items) > 1:
            self.log("⚠️ 저장할 항목 하나만 목록에서 선택하세요.")
            return

        item_id = selected_items[0]
        item_data = self.playlist_data.get(item_id)
        if not item_data or item_data['type'] != MacroType.MEMORY.value: return
        actions_to_save = item_data.get('data')
        if not actions_to_save:
            self.log("⚠️ 저장할 동작이 없습니다.")
            return
        file_path = filedialog.asksaveasfilename(initialfile=self.macro_tree.set(item_id, "#1").replace(".json", "") + ".json", defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not file_path: return
        try:
            with open(file_path, 'w', encoding='utf-8') as f: json.dump({'actions': actions_to_save}, f, indent=4)
            new_display_name = os.path.basename(file_path)
            self.macro_tree.set(item_id, "#1", new_display_name)
            self.macro_tree.item(item_id, tags=())
            self.playlist_data[item_id] = {'type': MacroType.FILE.value, 'data': file_path, 'display_name': new_display_name}
            self.app.log_event(f"💾 매크로 저장 완료: '{new_display_name}'")
            self.on_tree_select(None)
            self._set_dirty()
        except Exception as e:
            self.app.log_event(f"🔥 파일 저장 실패: {e}")

    def remove_selected_macro(self):
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.log("⚠️ 목록에서 제거할 항목을 선택하세요.")
            return
        for item in selected_items:
            if item in self.playlist_data: del self.playlist_data[item]
            self.macro_tree.delete(item)
        self.log(f"{len(selected_items)}개 항목을 재생 목록에서 제거했습니다.")
        self._set_dirty()

    def clear_macro_list(self, from_load=False):
        for item in self.macro_tree.get_children(): self.macro_tree.delete(item)
        self.playlist_data.clear()
        if not from_load:
            self.log("재생 목록을 모두 비웠습니다.")
            self._set_dirty()

    def move_macro_up(self):
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.log("⚠️ 이동할 항목을 선택하세요.")
            return
        for item in selected_items:
            self.macro_tree.move(item, self.macro_tree.parent(item), self.macro_tree.index(item) - 1)
        self._set_dirty()

    def move_macro_down(self):
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.log("⚠️ 이동할 항목을 선택하세요.")
            return
        for item in reversed(selected_items):
            self.macro_tree.move(item, self.macro_tree.parent(item), self.macro_tree.index(item) + 1)
        self._set_dirty()

class ChainGroupTab(ttk.Frame):
    def __init__(self, parent, app, config=None):
        super().__init__(parent)
        self.app = app
        callbacks = {
            'log': self.log,
            'update_ui': self.update_ui_state,
            'update_status': self.app.update_status,
            'load_macros_from_chain': self.load_macros_from_chain,
            'load_actions_from_file': self.app.recording_tab.load_actions_from_file
        }
        self.macro = ChainGroupMacro(callbacks)
        self.chain_playlist_data = {}
        self.current_group_path = None
        self.is_dirty = False
        self._create_widgets()
        if config:
            last_group = config.get('last_group')
            if last_group and os.path.isfile(last_group):
                self.load_group(path=last_group)

    def _set_dirty(self, dirty=True):
        if self.is_dirty == dirty: return
        self.is_dirty = dirty
        title = "푸크로 V4.2"
        if dirty: title += "*"
        self.app.root.title(title)

    def log(self, message):
        self.app.log(f"[그룹] {message}")

    def _create_widgets(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=(10,5))
        top_frame.columnconfigure((0, 1), weight=1)
        play_frame = ttk.LabelFrame(top_frame, text="재생")
        play_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0,5))
        play_frame.columnconfigure(0, weight=1)
        self.play_start_button = ttk.Button(play_frame, text="그룹 재생 시작 (F3)", command=self.start_group_playback)
        self.play_start_button.pack(fill=tk.X, padx=5, pady=5)
        self.pause_play_button = ttk.Button(play_frame, text="일시정지 (F5)", command=self.macro.pause_or_resume_playback, state=tk.DISABLED)
        self.pause_play_button.pack(fill=tk.X, padx=5, pady=5)
        self.play_stop_button = ttk.Button(play_frame, text="그룹 재생 중지 (F4)", command=self.macro.stop_playback, state=tk.DISABLED)
        self.play_stop_button.pack(fill=tk.X, padx=5, pady=5)
        group_io_frame = ttk.LabelFrame(top_frame, text="그룹 파일")
        group_io_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(5,0))
        self.load_group_button = ttk.Button(group_io_frame, text="불러오기", command=self.load_group)
        self.load_group_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_group_button = ttk.Button(group_io_frame, text="저장", command=self.save_group)
        self.save_group_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_as_group_button = ttk.Button(group_io_frame, text="다른 이름으로...", command=lambda: self.save_group(save_as=True))
        self.save_as_group_button.pack(fill=tk.X, padx=5, pady=5)
        playlist_frame = ttk.LabelFrame(self, text="매크로 그룹 편집기 (체인 재생 목록)")
        playlist_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        playlist_frame.columnconfigure(0, weight=1)
        playlist_frame.rowconfigure(0, weight=1)
        list_container = ttk.Frame(playlist_frame)
        list_container.grid(row=0, column=0, sticky='nsew', pady=5, padx=5)
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        columns = ("#1", "#2", "#3")
        # ✨ [다중 선택 기능] selectmode를 'extended'로 변경
        self.chain_tree = ttk.Treeview(list_container, columns=columns, show="headings", selectmode="extended")
        self.chain_tree.heading("#1", text="매크로 체인 파일")
        self.chain_tree.heading("#2", text="이 체인 반복 횟수")
        self.chain_tree.heading("#3", text="실행 후 대기(초)")
        self.chain_tree.column("#1", width=200)
        self.chain_tree.column("#2", width=100, anchor='center')
        self.chain_tree.column("#3", width=100, anchor='center')
        self.chain_tree.grid(row=0, column=0, sticky='nsew')
        self.chain_tree.bind("<Double-1>", self.on_tree_double_click)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.chain_tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.chain_tree['yscrollcommand'] = scrollbar.set
        btn_frame = ttk.Frame(playlist_frame)
        btn_frame.grid(row=0, column=1, sticky='ns', padx=(0, 5), pady=5)
        ttk.Button(btn_frame, text="체인 추가", command=self.add_chain_to_list).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="제거", command=self.remove_selected_chain).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="▲", command=self.move_chain_up).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="▼", command=self.move_chain_down).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="모두 삭제", command=self.clear_chain_list).pack(fill=tk.X, pady=2)
        self.play_settings_frame = ttk.LabelFrame(self, text="재생 설정 (전체 그룹)")
        self.play_settings_frame.pack(fill=tk.X, padx=10, pady=5)
        self.repeat_mode_var = tk.StringVar(value=RepeatMode.INFINITE.name)
        self.repeat_value_var = tk.StringVar(value="10")
        self.repeat_delay_var = tk.StringVar(value="1.0")
        self.playback_speed_var = tk.StringVar(value="1.0x")
        self.image_timeout_var = tk.StringVar(value="30")
        repeat_mode_frame = ttk.Frame(self.play_settings_frame)
        repeat_mode_frame.grid(row=0, column=0, columnspan=4, sticky='w', padx=5, pady=(5,0))
        ttk.Radiobutton(repeat_mode_frame, text="무한 반복", variable=self.repeat_mode_var, value=RepeatMode.INFINITE.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(repeat_mode_frame, text="횟수:", variable=self.repeat_mode_var, value=RepeatMode.COUNT.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_count_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_value_var, width=8)
        self.repeat_count_entry.pack(side=tk.LEFT, padx=(2, 10))
        ttk.Radiobutton(repeat_mode_frame, text="시간(분):", variable=self.repeat_mode_var, value=RepeatMode.DURATION.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_duration_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_value_var, width=8)
        self.repeat_duration_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(self.play_settings_frame, text="전체 그룹 반복 대기(초):").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(self.play_settings_frame, textvariable=self.repeat_delay_var, width=8).grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(self.play_settings_frame, text="재생 속도:").grid(row=1, column=2, sticky='w', padx=15, pady=2)
        self.speed_combo = ttk.Combobox(self.play_settings_frame, textvariable=self.playback_speed_var, values=["0.5x", "1.0x", "1.5x", "2.0x", "5.0x"], width=6)
        self.speed_combo.grid(row=1, column=3, sticky='w', pady=2)
        img_wait_frame = ttk.Frame(self.play_settings_frame)
        img_wait_frame.grid(row=2, column=0, columnspan=2, sticky='w', padx=5, pady=(2,5))
        ttk.Label(img_wait_frame, text="이미지 대기(초):").pack(side=tk.LEFT)
        ttk.Entry(self.play_settings_frame, textvariable=self.image_timeout_var, width=8).grid(row=2, column=1, sticky='w', pady=(2,5))
        self.toggle_repeat_entry()

    def start_group_playback(self):
        chain_playlist = []
        for item_id in self.chain_tree.get_children():
            path = self.chain_playlist_data.get(item_id)
            if path:
                try:
                    repeats = int(self.chain_tree.set(item_id, "#2"))
                    delay_after = float(self.chain_tree.set(item_id, "#3"))
                    chain_playlist.append({'path': path, 'repeats': repeats, 'delay_after': delay_after})
                except ValueError:
                    self.log(f"⚠️ '{os.path.basename(path)}'의 반복 횟수 또는 대기 시간 값이 잘못되었습니다.")
                    return
        if not chain_playlist:
            self.log("⚠️ 그룹 재생 목록에 체인을 추가해주세요.")
            return
        try:
            speed_str = self.playback_speed_var.get().replace('x', '')
            settings = {
                'chain_playlist': chain_playlist,
                'repeat_mode': RepeatMode[self.repeat_mode_var.get()],
                'repeat_value': int(self.repeat_value_var.get()),
                'repeat_delay': float(self.repeat_delay_var.get()),
                'playback_speed': float(speed_str),
                'image_timeout': int(self.image_timeout_var.get()),
                'app': self.app,
                'tree': self.app.recording_tab.macro_tree
            }
            self.macro.start_playback(settings)
        except (ValueError, TypeError):
            self.log("⚠️ 그룹 재생 설정 값이 올바르지 않습니다. (숫자 확인)")

    def load_macros_from_chain(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f: chain_content = json.load(f)
            playlist = []
            chain_dir = os.path.dirname(file_path)
            for item in chain_content.get('playlist', []):
                item_type = item.get('type')
                item_data = item.get('data')
                if item_type in [MacroType.FILE.value, MacroType.IMAGE_WAIT.value] and not os.path.isabs(item_data):
                    item_data = os.path.normpath(os.path.join(chain_dir, item_data))
                playlist.append({'type': item_type, 'data': item_data, 'display_name': item.get('display_name'), 'delay': item.get('delay', '1.0')})
            return playlist
        except FileNotFoundError:
            self.log(f"🔥 그룹 실행 중 체인 파일 없음: '{os.path.basename(file_path)}'")
            return None
        except Exception as e:
            self.log(f"🔥 그룹 실행 중 체인 로드 실패: '{os.path.basename(file_path)}' ({e})")
            return None

    def add_chain_to_list(self):
        files = filedialog.askopenfilenames(title="매크로 체인 파일 추가", filetypes=[("Pucro Chain files", "*.pchain")])
        if files:
            for file_path in files:
                display_name = os.path.basename(file_path)
                item_id = self.chain_tree.insert("", tk.END, values=(display_name, "1", "1.0"))
                self.chain_playlist_data[item_id] = file_path
            self.log(f"✅ {len(files)}개 체인을 그룹에 추가했습니다.")
            self._set_dirty()

    def remove_selected_chain(self):
        selected_items = self.chain_tree.selection()
        if not selected_items: return
        for item in selected_items:
            if item in self.chain_playlist_data: del self.chain_playlist_data[item]
            self.chain_tree.delete(item)
        self._set_dirty()

    def clear_chain_list(self, from_load=False):
        for item in self.chain_tree.get_children(): self.chain_tree.delete(item)
        self.chain_playlist_data.clear()
        if not from_load:
            self.log("그룹 목록을 모두 비웠습니다.")
            self._set_dirty()

    def move_chain_up(self):
        selected = self.chain_tree.selection()
        if not selected: return
        for item in selected:
            self.chain_tree.move(item, self.chain_tree.parent(item), self.chain_tree.index(item) - 1)
        self._set_dirty()

    def move_chain_down(self):
        selected = self.chain_tree.selection()
        if not selected: return
        for item in reversed(selected):
            self.chain_tree.move(item, self.chain_tree.parent(item), self.chain_tree.index(item) + 1)
        self._set_dirty()

    def on_tree_double_click(self, event):
        if self.macro.is_playing: return
        region = self.chain_tree.identify("region", event.x, event.y)
        if region != "cell": return
        column = self.chain_tree.identify_column(event.x)
        selected_item = self.chain_tree.focus()
        if not selected_item: return
        if column in ["#2", "#3"]:
            column_box = self.chain_tree.bbox(selected_item, column)
            entry = ttk.Entry(self.chain_tree, justify='center')
            entry.insert(0, self.chain_tree.set(selected_item, column))
            entry.select_range(0, tk.END)
            entry.focus()
            entry.place(x=column_box[0], y=column_box[1], w=column_box[2], h=column_box[3])
            def on_enter(e):
                self.chain_tree.set(selected_item, column, entry.get())
                entry.destroy()
                self._set_dirty()
            entry.bind("<Return>", on_enter)
            entry.bind("<FocusOut>", lambda e: entry.destroy())

    def save_group(self, save_as=False):
        if not self.chain_playlist_data:
            self.log("⚠️ 저장할 그룹이 없습니다.")
            return False
        file_path = self.current_group_path
        if save_as or not file_path:
            file_path = filedialog.asksaveasfilename(title="매크로 그룹 저장", defaultextension=".pgroup", filetypes=[("Pucro Group files", "*.pgroup"), ("All files", "*.*")])
        if not file_path: return False
        self.current_group_path = file_path
        group_content = {'settings': {'repeat_mode': self.repeat_mode_var.get(), 'repeat_value': self.repeat_value_var.get(), 'repeat_delay': self.repeat_delay_var.get(), 'playback_speed': self.playback_speed_var.get(), 'image_timeout': self.image_timeout_var.get()}, 'playlist': []}
        group_dir = os.path.dirname(file_path)
        for item_id in self.chain_tree.get_children():
            chain_path = self.chain_playlist_data.get(item_id)
            if not chain_path: continue
            try: rel_path = os.path.relpath(chain_path, group_dir)
            except ValueError: rel_path = chain_path
            group_item = {'path': rel_path, 'repeats': self.chain_tree.set(item_id, "#2"), 'delay_after': self.chain_tree.set(item_id, "#3")}
            group_content['playlist'].append(group_item)
        try:
            with open(file_path, 'w', encoding='utf-8') as f: json.dump(group_content, f, indent=4, ensure_ascii=False)
            self.app.log_event(f"💾 그룹 저장 완료: '{os.path.basename(file_path)}'")
            self._set_dirty(False)
            return True
        except Exception as e:
            self.app.log_event(f"🔥 그룹 저장 실패: {e}")
            return False

    def load_group(self, path=None):
        if self.is_dirty:
            if not messagebox.askyesno("확인", "저장되지 않은 변경사항이 있습니다. 계속 진행하시겠습니까?"): return
        file_path = path
        if not file_path:
            file_path = filedialog.askopenfilename(title="매크로 그룹 불러오기", filetypes=[("Pucro Group files", "*.pgroup"), ("All files", "*.*")])
        if not file_path: return
        self.current_group_path = file_path
        try:
            with open(file_path, 'r', encoding='utf-8') as f: group_content = json.load(f)
            self.clear_chain_list(from_load=True)
            settings = group_content.get('settings', {})
            self.repeat_mode_var.set(settings.get('repeat_mode', RepeatMode.INFINITE.name))
            self.repeat_value_var.set(settings.get('repeat_value', '10'))
            self.repeat_delay_var.set(settings.get('repeat_delay', '1.0'))
            self.playback_speed_var.set(settings.get('playback_speed', '1.0x'))
            self.image_timeout_var.set(settings.get('image_timeout', '30'))
            self.toggle_repeat_entry()
            group_dir = os.path.dirname(file_path)
            for item in group_content.get('playlist', []):
                chain_path = item.get('path')
                if not os.path.isabs(chain_path):
                    chain_path = os.path.normpath(os.path.join(group_dir, chain_path))
                item_id = self.chain_tree.insert("", tk.END, values=(os.path.basename(chain_path), item.get('repeats', '1'), item.get('delay_after', '1.0')))
                self.chain_playlist_data[item_id] = chain_path
            self.app.log_event(f"💾 그룹 불러오기 완료: '{os.path.basename(file_path)}'")
            self._set_dirty(False)
        except Exception as e:
            self.app.log_event(f"🔥 그룹 불러오기 실패: {e}")
            messagebox.showerror("오류", f"그룹 파일을 불러오는 중 오류가 발생했습니다.\n{e}")

    def toggle_repeat_entry(self):
        try:
            if not self.play_settings_frame.winfo_exists(): return
            mode = self.repeat_mode_var.get()
            self.repeat_count_entry.config(state=tk.NORMAL if mode == RepeatMode.COUNT.name else tk.DISABLED)
            self.repeat_duration_entry.config(state=tk.NORMAL if mode == RepeatMode.DURATION.name else tk.DISABLED)
        except tk.TclError: pass

    def update_ui_state(self, playing=None, paused=None):
        try:
            is_playing = playing if playing is not None else self.macro.is_playing
            state = tk.DISABLED if is_playing else tk.NORMAL
            self.play_start_button.config(state=state)
            self.load_group_button.config(state=state)
            self.save_group_button.config(state=state)
            self.save_as_group_button.config(state=state)
            self.play_stop_button.config(state=tk.NORMAL if is_playing else tk.DISABLED)
            self.pause_play_button.config(state=tk.NORMAL if is_playing else tk.DISABLED)
            for child in self.play_settings_frame.winfo_children():
                if hasattr(child, 'config'): child.config(state=state)
            self.toggle_repeat_entry()
            if paused is not None:
                self.pause_play_button.config(text="재개 (F5)" if paused else "일시정지 (F5)")
        except tk.TclError: pass

class PatchNotesTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self._create_widgets()

    def _create_widgets(self):
        notes_frame = ttk.LabelFrame(self, text="버전 정보 및 변경 사항")
        notes_frame.pack(fill=tk.BOTH, expand=True)
        notes_text_widget = scrolledtext.ScrolledText(notes_frame, wrap=tk.WORD, padx=10, pady=10, bd=0)
        notes_text_widget.pack(fill=tk.BOTH, expand=True)
        notes_text_widget.tag_configure("title", font=("", 12, "bold"), spacing3=10)
        notes_text_widget.tag_configure("subtitle", font=("", 10, "bold"), spacing1=10, lmargin1=5)
        notes_text_widget.tag_configure("item", lmargin1=15, lmargin2=15, spacing1=2)

        notes_text_widget.insert(tk.END, "푸크로 v4.2\n", "title")
        notes_text_widget.insert(tk.END, "주요 변경사항 (편의성 개선)\n", "subtitle")
        notes_text_widget.insert(tk.END, "• ✨ [피드백] 매크로 실행 시 현재 동작이 목록에서 하이라이트됩니다. (클릭 위치 표시는 성능 문제로 제거)\n", "item")
        notes_text_widget.insert(tk.END, "• ✨ [테스트] 매크로 체인 목록에서 항목을 하나만 선택하여 테스트 실행하는 기능이 추가되었습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• ✨ [UI/UX] 프로그램을 닫을 때 시스템 트레이로 최소화되며, 시작/종료 시 알림이 표시됩니다.\n", "item")
        notes_text_widget.insert(tk.END, "• ✨ [UI/UX] 목록에서 Shift, Ctrl 키 등으로 여러 항목을 선택하여 한 번에 제거할 수 있습니다.\n", "item")
        notes_text_widget.insert(tk.END, "\n푸크로 v4.1\n", "title")
        notes_text_widget.insert(tk.END, "주요 변경사항\n", "subtitle")
        notes_text_widget.insert(tk.END, "• ✨ [핵심 기능] '매크로 그룹'을 파일(.pgroup)로 저장하고 불러오는 기능을 추가했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• ✨ [편의성] 마지막으로 사용한 탭과 그룹 파일을 기억하여 다음 실행 시 자동으로 불러옵니다.\n", "item")
        notes_text_widget.insert(tk.END, "• ✨ [안정성] 그룹 수정 후 저장하지 않고 종료 시, 저장 여부를 확인합니다.\n", "item")
        notes_text_widget.config(state=tk.DISABLED)

class InfoTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self._create_widgets()

    def _create_widgets(self):
        link_container = tk.Frame(self)
        link_container.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        source_text_label = tk.Label(link_container, text="개발자 블로그 (출처): ")
        source_text_label.pack(side=tk.LEFT, padx=(0, 2))
        url = "https://blog.naver.com/skarbs01/223987760034"
        link_label = tk.Label(link_container, text=url, fg="blue", cursor="hand2")
        link_label.pack(side=tk.LEFT)
        f = tkFont.Font(link_label, link_label.cget("font"))
        f.configure(underline=True)
        link_label.configure(font=f)
        link_label.bind("<Button-1>", lambda e: webbrowser.open_new(url))
        info_frame = ttk.LabelFrame(self, text="푸크로 (Pucro) 매크로 - 초보자 안내서")
        info_frame.pack(fill=tk.BOTH, expand=True)
        help_text = scrolledtext.ScrolledText(info_frame, wrap=tk.WORD, padx=10, pady=10, bd=0, font=("Malgun Gothic", 10))
        help_text.pack(fill=tk.BOTH, expand=True)
        help_text.tag_configure("title", font=("Malgun Gothic", 12, "bold"), spacing3=10, lmargin1=5)
        help_text.tag_configure("subtitle", font=("Malgun Gothic", 10, "bold"), spacing1=5, lmargin1=10)
        help_text.tag_configure("item", lmargin1=20, lmargin2=20, spacing1=3)
        help_text.tag_configure("bold", font=("Malgun Gothic", 10, "bold"))
        help_text.tag_configure("highlight", background="#FFFDE4", lmargin1=20, lmargin2=20)
        help_text.insert(tk.END, "🤖 매크로가 처음이신가요?\n", "title")
        help_text.insert(tk.END, "매크로는 간단히 말해 '컴퓨터 작업 자동화' 프로그램입니다.\n사용자의 마우스 클릭, 키보드 입력을 그대로 녹화했다가, 필요할 때마다 똑같이 반복 재생해주는 편리한 기능이죠.\n마치 컴퓨터를 위한 로봇 비서라고 생각하시면 쉽습니다.\n\n", "item")
        help_text.insert(tk.END, "이 프로그램의 주요 기능:\n", "subtitle")
        help_text.insert(tk.END, "•  매크로 체인: 마우스/키보드 움직임을 녹화하고, 이미지 찾기 같은 명령을 조합하여 하나의 작업 흐름(.pchain)을 만듭니다.\n•  매크로 그룹: 여러 개의 '매크로 체인'을 묶어서 더 복잡하고 긴 작업을 순서대로 자동화(.pgroup)할 수 있습니다.\n•  이미지 매크로: 화면에서 특정 이미지를 찾아 클릭하는, 가장 간단한 방식의 매크로입니다.\n", "item")
        help_text.insert(tk.END, "\n⭐ 가장 중요! '관리자 권한'으로 실행하기\n", "title")
        help_text.insert(tk.END, "특히 게임에서 매크로를 사용하려면 이 설정이 필수입니다.\n", "item")
        help_text.insert(tk.END, "왜 필요한가요?\n", "subtitle")
        help_text.insert(tk.END, "대부분의 게임은 높은 보안 수준(권한)으로 실행됩니다. 매크로가 게임 안을 들여다보고 클릭하려면, 게임과 동등하거나 더 높은 '관리자 권한'이 필요하기 때문입니다. 이 권한이 없으면 매크로가 게임창을 인식하지 못해 아무런 반응을 하지 않습니다.\n\n", "item")
        help_text.insert(tk.END, "영구 설정 방법 (한 번만 하면 됩니다):\n", "subtitle")
        help_text.insert(tk.END, "1. 푸크로 프로그램 파일(.exe)을 마우스 오른쪽 버튼으로 클릭\n2. '속성' 메뉴 선택\n3. '호환성' 탭으로 이동\n4. '관리자 권한으로 이 프로그램 실행' 옵션을 체크하고 '확인'\n", "item")
        help_text.insert(tk.END, "\n💡 주요 기능 상세 설명\n", "title")
        help_text.insert(tk.END, "'이미지 대기(초)'는 무엇인가요?\n", "subtitle")
        help_text.insert(tk.END, "매크로 체인 재생 시, 특정 이미지가 화면에 나타날 때까지 '최대 몇 초까지 기다릴지' 정하는 시간입니다.\n\n예시: '이미지 대기'를 30초로 설정하고 '물약' 이미지를 기다리는 동작을 추가했다면?\n→ 30초 안에 '물약' 이미지가 보이면 즉시 다음 동작으로 넘어갑니다.\n→ 30초가 지나도 이미지가 안 보이면, 기다리는 것을 포기하고 다음 동작으로 넘어갑니다.\n\n", "item")
        help_text.insert(tk.END, "'실행 후 대기(초)'와의 차이점:\n'실행 후 대기'는 동작 성공 여부와 관계없이 무조건 지정된 시간만큼 쉬는 고정적인 휴식 시간입니다.\n", "highlight")
        help_text.insert(tk.END, "\n'상대 경로' - 파일 관리 꿀팁\n", "subtitle")
        help_text.insert(tk.END, "매크로 체인(.pchain)이나 그룹(.pgroup)을 저장하면, 그 안에 포함된 녹화 파일이나 이미지 파일의 위치가 '상대 경로'로 저장됩니다.\n\n이게 왜 좋을까요?\n", "item")
        help_text.insert(tk.END, "모든 관련 파일(체인, 그룹, 녹화, 이미지)을 하나의 폴더에 같이 넣어두기만 하면, 이 폴더를 통째로 다른 컴퓨터로 옮기거나 USB에 담아도 경로 문제 없이 바로 사용할 수 있습니다. 파일 경로를 일일이 수정할 필요가 없어 매우 편리합니다.\n", "item")
        help_text.config(state=tk.DISABLED)

class GlobalAreaSelector:
    def __init__(self, tab):
        self.tab = tab
        self.start_pos = None
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press)
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def is_alive(self):
        return self.mouse_listener.is_alive()

    def on_press(self, key):
        if key == keyboard.Key.esc:
            self.tab.log("영역 설정을 취소했습니다.")
            self.tab.app.update_status("준비")
            self.cleanup()

    def on_click(self, x, y, button, pressed):
        if button != mouse.Button.left or not pressed: return
        if self.start_pos is None:
            self.start_pos = (x, y)
            self.tab.log(f"시작점 설정: {self.start_pos}")
        else:
            end_pos = (x, y)
            left = min(self.start_pos[0], end_pos[0])
            top = min(self.start_pos[1], end_pos[1])
            width = abs(self.start_pos[0] - end_pos[0])
            height = abs(self.start_pos[1] - end_pos[1])
            if width > 0 and height > 0: self.tab.set_area(left, top, width, height)
            else: self.tab.log("⚠️ 영역이 유효하지 않습니다. 다시 시도해주세요.")
            self.cleanup()

    def cleanup(self):
        if self.mouse_listener: self.mouse_listener.stop()
        if self.keyboard_listener: self.keyboard_listener.stop()

# --- 5. 메인 애플리케이션 클래스 ---
class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("푸크로 V4.2")
        self.config_path = os.path.join(os.path.expanduser("~"), ".pucro_config.json")
        self.config = self.load_config()
        self.root.geometry(self.config.get("geometry", "1100x750"))
        self.style = ttk.Style(self.root)
        try: self.style.theme_use('clam')
        except tk.TclError: print("'clam' 테마를 찾을 수 없습니다. 기본 테마로 실행합니다.")
        self.style.configure("Treeview.Heading", font=(None, 10, 'bold'))
        self.style.configure("TButton", padding=5)
        self.style.configure("TMenubutton", padding=5)
        self.hotkey_listener = None
        self.tray_icon = None
        self._create_widgets()
        self._setup_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"설정 파일 로드 오류: {e}")
        return {}

    def save_config(self):
        try:
            config_data = {
                "geometry": self.root.geometry(),
                "image_tab": {"last_folder": self.image_tab.image_folder_path.get()},
                "record_tab": {"last_chain": self.recording_tab.current_chain_path},
                "group_tab": {"last_group": self.group_tab.current_group_path},
                "last_tab_index": self.notebook.index(self.notebook.select())
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)
        except (IOError, tk.TclError) as e:
            print(f"설정 파일 저장 오류: {e}")

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=2)
        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5, padx=(0, 5))
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        log_container = ttk.Frame(right_frame)
        log_container.pack(fill=tk.BOTH, expand=True, pady=5, padx=(5, 0))
        log_container.columnconfigure(0, weight=1)
        log_container.rowconfigure(1, weight=1)
        event_log_frame = ttk.LabelFrame(log_container, text="이벤트 로그")
        event_log_frame.grid(row=0, column=0, sticky='ew')
        event_log_frame.columnconfigure(0, weight=1)
        self.event_log_text = scrolledtext.ScrolledText(event_log_frame, wrap=tk.WORD, height=8, state=tk.DISABLED, bd=0)
        self.event_log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        run_log_frame = ttk.LabelFrame(log_container, text="실행 로그")
        run_log_frame.grid(row=1, column=0, sticky='nsew', pady=(5,0))
        run_log_frame.columnconfigure(0, weight=1)
        run_log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(run_log_frame, wrap=tk.WORD, state=tk.DISABLED, bd=0)
        self.log_text.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        ttk.Button(run_log_frame, text="로그 지우기", command=self.clear_log).grid(row=1, column=0, sticky='e', padx=5, pady=(0,5))
        self.status_var = tk.StringVar(value="준비")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        tab_record = ttk.Frame(self.notebook)
        tab_group = ttk.Frame(self.notebook)
        tab_image = ttk.Frame(self.notebook)
        tab_patch = ttk.Frame(self.notebook)
        tab_info = ttk.Frame(self.notebook)
        self.notebook.add(tab_record, text="  매크로 체인  ")
        self.notebook.add(tab_group, text="  매크로 그룹  ")
        self.notebook.add(tab_image, text="  이미지 매크로  ")
        self.notebook.add(tab_patch, text="  패치노트  ")
        self.notebook.add(tab_info, text="  도움말  ")
        self.recording_tab = RecordingMacroTab(tab_record, self, config=self.config.get('record_tab'))
        self.recording_tab.pack(fill=tk.BOTH, expand=True)
        self.group_tab = ChainGroupTab(tab_group, self, config=self.config.get('group_tab'))
        self.group_tab.pack(fill=tk.BOTH, expand=True)
        self.image_tab = ImageMacroTab(tab_image, self, config=self.config.get('image_tab'))
        self.image_tab.pack(fill=tk.BOTH, expand=True)
        self.patch_notes_tab = PatchNotesTab(tab_patch)
        self.patch_notes_tab.pack(fill=tk.BOTH, expand=True)
        self.info_tab = InfoTab(tab_info)
        self.info_tab.pack(fill=tk.BOTH, expand=True)
        try:
            last_tab_index = int(self.config.get("last_tab_index", 0))
            if last_tab_index < len(self.notebook.tabs()):
                self.notebook.select(last_tab_index)
        except (ValueError, IndexError): self.notebook.select(0)
        self.log("프로그램 준비 완료. 사용할 탭을 선택하고 시작하세요.")

    def _setup_hotkeys(self):
        try:
            self.hotkey_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
            self.hotkey_listener.start()
            self.log("전역 단축키 활성화. (활성 탭에 따라 동작)")
        except Exception as e:
            self.log(f"🔥 단축키 설정 실패: {e}")
            self.log("ℹ️ 관리자 권한으로 실행하거나 접근성 권한을 확인하세요.")

    def _on_key_press(self, key):
        try:
            if not self.root.winfo_exists(): return
            if self.recording_tab.macro.is_recording:
                if key == keyboard.Key.f2: self.root.after(0, self.recording_tab.record_stop_button.invoke)
                return
            current_tab_index = self.notebook.index(self.notebook.select())
            if current_tab_index == 0:
                if key == keyboard.Key.f1: self.root.after(0, self.recording_tab.record_start_button.invoke)
                elif key == keyboard.Key.f2: self.root.after(0, self.recording_tab.record_stop_button.invoke)
                elif key == keyboard.Key.f3: self.root.after(0, self.recording_tab.play_start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.recording_tab.play_stop_button.invoke)
                elif key == keyboard.Key.f5: self.root.after(0, self.recording_tab.pause_play_button.invoke)
            elif current_tab_index == 1:
                if key == keyboard.Key.f3: self.root.after(0, self.group_tab.play_start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.group_tab.play_stop_button.invoke)
                elif key == keyboard.Key.f5: self.root.after(0, self.group_tab.pause_play_button.invoke)
            elif current_tab_index == 2:
                if key == keyboard.Key.f3: self.root.after(0, self.image_tab.start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.image_tab.stop_button.invoke)
                elif key == keyboard.Key.f5: self.root.after(0, self.image_tab.pause_button.invoke)
                elif key == keyboard.Key.f9: self.root.after(0, self.image_tab.start_defining_area)
        except Exception: pass

    def _on_key_release(self, key):
        try:
            if self.recording_tab.macro.is_recording: self.recording_tab.macro._on_release(key)
        except Exception: pass

    def _on_closing(self):
        if self.recording_tab.is_dirty or self.group_tab.is_dirty:
            if not messagebox.askyesno("종료 확인", "저장되지 않은 변경사항이 있습니다. 저장하지 않고 종료하시겠습니까?"):
                return
        self.hide_to_tray()

    def setup_tray_icon(self):
        try:
            image = PILImage.open("icon.ico")
        except FileNotFoundError:
            width, height = 64, 64
            image = PILImage.new('RGB', (width, height), color = 'blue')
        menu = (pystray.MenuItem('보이기', self.show_from_tray, default=True), pystray.MenuItem('종료', self.quit_app))
        self.tray_icon = pystray.Icon("Pucro", image, "Pucro 매크로", menu)
        self.tray_icon.run()

    def hide_to_tray(self):
        self.root.withdraw()
        if not self.tray_icon or not self.tray_icon.visible:
            threading.Thread(target=self.setup_tray_icon, daemon=True).start()
            self.notify("프로그램이 시스템 트레이에서 실행 중입니다.")

    def show_from_tray(self):
        if self.tray_icon: self.tray_icon.stop()
        self.root.after(0, self.root.deiconify)

    def quit_app(self):
        if self.tray_icon: self.tray_icon.stop()
        self.save_config()
        if self.hotkey_listener and self.hotkey_listener.is_alive():
            self.hotkey_listener.stop()
        self.root.destroy()

    def notify(self, message, title="Pucro 매크로"):
        if self.tray_icon and self.tray_icon.visible:
            self.tray_icon.notify(message, title)

    def update_tree_selection(self, tree, item_id):
        try:
            if tree.exists(item_id):
                tree.selection_set(item_id)
                tree.focus(item_id)
                tree.see(item_id)
        except tk.TclError: pass

    def log(self, message):
        self.root.after(0, self._log_update, self.log_text, message)
        if "🚀" in message or "🛑" in message or "👍" in message:
            self.notify(message)

    def log_event(self, message):
        self.root.after(0, self._log_update, self.event_log_text, message)
        if "🔥" in message or "⚠️" in message:
            self.notify(message)

    def _log_update(self, text_widget, message):
        try:
            if not text_widget.winfo_exists(): return
            text_widget.config(state=tk.NORMAL)
            text_widget.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
            text_widget.see(tk.END)
            text_widget.config(state=tk.DISABLED)
        except tk.TclError: pass

    def clear_log(self):
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log("로그 창을 초기화했습니다.")
        except tk.TclError: pass

    def update_status(self, message):
        self.status_var.set(message)

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()