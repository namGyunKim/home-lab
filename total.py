# 필요한 라이브러리를 불러옵니다.
import pyautogui
import time
import glob
import os
import sys
from PIL import Image
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import threading
import json
import re
from collections import deque

# pynput 라이브러리가 필요합니다. 설치: pip install pynput
try:
    from pynput import mouse, keyboard
except ImportError:
    print("오류: pynput 라이브러리가 필요합니다. 'pip install pynput' 명령어로 설치해주세요.")
    sys.exit()

# --- 이미지 매크로 실행 로직 ---
def execute_image_scan(log_func, image_folder_path, stop_event):
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

# --- 1. 이미지 매크로 로직 클래스 ---
class AutoClickerMacro:
    def __init__(self, tab_instance):
        self.tab = tab_instance
        self.is_running = False
        self.macro_thread = None
        self.stop_event = threading.Event()

    def start(self):
        if self.is_running:
            self.tab.log("⚠️ 이미 이미지 매크로가 실행 중입니다.")
            return

        if not self.tab.image_folder_path.get():
            self.tab.log("⚠️ 먼저 이미지 폴더를 선택해주세요.")
            return

        self.tab.save_settings()
        self.is_running = True
        self.stop_event.clear()
        self.macro_thread = threading.Thread(target=self.run_macro, daemon=True)
        self.macro_thread.start()
        self.tab.update_ui_state(running=True)

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        self.stop_event.set()
        self.tab.update_ui_state(running=False)
        self.tab.log("이미지 매크로 중지를 요청했습니다...")

    def run_macro(self):
        self.tab.log("🚀 이미지 매크로를 시작합니다...")
        self.tab.app.update_status("이미지 매크로 실행 중...")
        try:
            while self.is_running:
                image_folder = self.tab.image_folder_path.get()
                repeat_delay = float(self.tab.repeat_delay_var.get())
                
                execute_image_scan(self.tab.log, image_folder, self.stop_event)

                if not self.is_running: break

                self.tab.log(f"👍 순회 완료. {repeat_delay}초 후 다시 시작.")
                self.stop_event.wait(timeout=repeat_delay)

        except Exception as e:
            self.tab.log(f"🔥 매크로 실행 중 치명적 오류: {e}")

        self.is_running = False
        self.tab.update_ui_state(running=False)
        self.tab.log("🛑 이미지 매크로가 중지되었습니다.")
        self.tab.app.update_status("준비")


# --- 2. 녹화 매크로 로직 클래스 ---
class RecordingMacro:
    def __init__(self, tab_instance):
        self.tab = tab_instance
        self.recorded_actions = []
        self.playlist = []
        self.is_recording = False
        self.is_playing = False
        self.playback_thread = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.last_action_time = None
        self.is_mouse_down = False
        self.stop_event = threading.Event()

    def start_recording(self):
        if self.is_recording:
            self.tab.log("⚠️ 이미 녹화가 진행 중입니다.")
            return
        self.is_recording = True
        self.is_mouse_down = False
        self.recorded_actions = []
        self.last_action_time = time.time()

        self.mouse_listener = mouse.Listener(on_click=self._on_click, on_move=self._on_move)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

        self.mouse_listener.start()
        self.keyboard_listener.start()

        self.tab.update_ui_state(recording=True)
        self.tab.log("🔴 녹화를 시작합니다... (마우스와 키보드 입력 기록)")

    def stop_recording(self):
        if not self.is_recording: return
        if self.mouse_listener: self.mouse_listener.stop()
        if self.keyboard_listener: self.keyboard_listener.stop()

        self.is_recording = False
        self.tab.update_ui_state(recording=False)
        self.tab.log(f"⏹️ 녹화 중지. {len(self.recorded_actions)}개 동작 기록됨.")
        
        if self.recorded_actions:
            self.tab.add_memory_macro_to_list(self.recorded_actions)
            self.recorded_actions = []

    def _get_key_str(self, key):
        if hasattr(key, 'char'): return key.char
        elif hasattr(key, 'name'): return key.name.lower()
        return None

    def _on_press(self, key):
        if not self.is_recording: return
        if isinstance(key, keyboard.Key) and 'f' in key.name and key.name[1:].isdigit(): return

        key_str = self._get_key_str(key)
        if key_str:
            current_time = time.time()
            delay = current_time - self.last_action_time
            self.last_action_time = current_time
            action = {'type': 'key_down', 'key': key_str, 'delay': delay}
            self.recorded_actions.append(action)

    def _on_release(self, key):
        if not self.is_recording: return
        if isinstance(key, keyboard.Key) and 'f' in key.name and key.name[1:].isdigit(): return

        key_str = self._get_key_str(key)
        if key_str:
            current_time = time.time()
            delay = current_time - self.last_action_time
            self.last_action_time = current_time
            action = {'type': 'key_up', 'key': key_str, 'delay': delay}
            self.recorded_actions.append(action)

    def _on_click(self, x, y, button, pressed):
        if not self.is_recording: return
        self.is_mouse_down = pressed
        current_time = time.time()
        delay = current_time - self.last_action_time
        self.last_action_time = current_time
        action = {'type': 'mouse_down' if pressed else 'mouse_up', 'pos': (x, y), 'button': str(button).replace('Button.', ''), 'delay': delay}
        self.recorded_actions.append(action)

    def _on_move(self, x, y):
        if self.is_recording and self.is_mouse_down:
            current_time = time.time()
            delay = current_time - self.last_action_time
            self.last_action_time = current_time
            action = {'type': 'move', 'pos': (x, y), 'delay': delay}
            self.recorded_actions.append(action)

    def start_playback(self, playlist):
        if self.is_playing:
            self.tab.log("⚠️ 이미 재생 중입니다.")
            return
        if not playlist:
            self.tab.log("⚠️ 재생 목록이 비어있습니다.")
            return
        self.playlist = playlist
        self.is_playing = True
        self.stop_event.clear()
        self.playback_thread = threading.Thread(target=self.run_playback, daemon=True)
        self.playback_thread.start()
        self.tab.update_ui_state(playing=True)

    def stop_playback(self):
        if not self.is_playing: return
        self.is_playing = False
        self.stop_event.set()
        self.tab.log("재생 중지를 요청했습니다...")

    def run_playback(self):
        self.tab.log("🚀 매크로 체인 재생을 시작합니다...")
        self.tab.app.update_status("녹화 매크로 재생 중...")
        pyautogui.PAUSE = 0
        try:
            while self.is_playing:
                for item_index, item_info in enumerate(self.playlist):
                    if not self.is_playing: break
                    
                    macro_type = item_info['type']
                    macro_data = item_info['data']
                    individual_delay = item_info['delay']
                    display_name = item_info['display_name']

                    self.tab.log(f"▶️ ({item_index+1}/{len(self.playlist)}) '{display_name}' 재생 시작...")
                    
                    if macro_type == 'image_wait':
                        self.tab.log(f"⌛ '{os.path.basename(macro_data)}' 이미지를 찾는 중...")
                        while self.is_playing:
                            try:
                                img = Image.open(macro_data)
                                location = pyautogui.locateOnScreen(img, confidence=0.8)
                                if location:
                                    self.tab.log(f"✅ '{os.path.basename(macro_data)}' 발견. 다음 동작 대기...")
                                    break 
                                else:
                                    self.stop_event.wait(0.5)
                            except Exception as e:
                                self.tab.log(f"🔥 이미지 대기 중 오류: {e}")
                                self.stop_event.wait(1)
                    else: # 'file' 또는 'memory' 타입
                        actions = []
                        if macro_type == 'file':
                            try:
                                with open(macro_data, 'r', encoding='utf-8') as f: data = json.load(f)
                                actions = data.get('actions', [])
                            except Exception as e:
                                self.tab.log(f"🔥 '{display_name}' 파일 로드 실패: {e}")
                                continue
                        elif macro_type == 'memory':
                            actions = macro_data

                        if not actions:
                            self.tab.log(f"⚠️ '{display_name}'에 실행할 동작이 없습니다.")
                            continue

                        for i, action in enumerate(actions):
                            if not self.is_playing: break
                            self.stop_event.wait(action['delay'])
                            if not self.is_playing: break
                            
                            action_type = action['type']
                            if action_type == 'move': pyautogui.moveTo(action['pos'], duration=0)
                            elif action_type == 'mouse_down':
                                pyautogui.moveTo(action['pos'], duration=0)
                                pyautogui.mouseDown(button=action['button'])
                            elif action_type == 'mouse_up':
                                pyautogui.moveTo(action['pos'], duration=0)
                                pyautogui.mouseUp(button=action['button'])
                            elif action_type == 'key_down': pyautogui.keyDown(action['key'])
                            elif action_type == 'key_up': pyautogui.keyUp(action['key'])
                    
                    if self.is_playing and item_index < len(self.playlist) - 1:
                        try:
                            chain_delay = float(individual_delay)
                            if chain_delay > 0:
                                self.tab.log(f"🔗 다음 매크로까지 {chain_delay}초 대기...")
                                self.stop_event.wait(timeout=chain_delay)
                        except (ValueError, TypeError):
                            self.tab.log(f"⚠️ 매크로 간 간격 값 '{individual_delay}'이(가) 잘못되었습니다.")
                        except Exception as e:
                            self.tab.log(f"🔥 매크로 간 대기 중 오류: {e}")
                
                if not self.is_playing: break
                
                repeat_delay = float(self.tab.repeat_delay_var.get())
                self.tab.log(f"👍 재생 목록 완료. {repeat_delay}초 후 반복.")
                self.stop_event.wait(timeout=repeat_delay)

        except Exception as e:
            self.tab.log(f"🔥 재생 중 오류: {e}")
        
        self.is_playing = False
        self.tab.update_ui_state(playing=False)
        self.tab.log("🛑 매크로 재생이 중지되었습니다.")
        self.tab.app.update_status("준비")

# --- 3. 각 탭의 GUI를 구성하는 클래스 ---
class ImageMacroTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.macro = AutoClickerMacro(self)
        self._create_widgets()
        self.area_selector = None

    def log(self, message):
        self.app.log(f"[이미지] {message}")

    def _create_widgets(self):
        settings_frame = ttk.LabelFrame(self, text="이미지 매크로 설정")
        settings_frame.pack(fill=tk.X, padx=10, pady=5, anchor=tk.N)

        self.image_folder_path = tk.StringVar()
        self.interval_var = tk.StringVar(value="0.1")
        self.confidence_var = tk.StringVar(value="0.7")
        self.repeat_delay_var = tk.StringVar(value="1.0")
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
        ttk.Label(settings_frame, text="반복 대기(초):").grid(row=r, column=0, sticky=tk.W, padx=5, pady=2)
        self.repeat_delay_entry = ttk.Entry(settings_frame, textvariable=self.repeat_delay_var, width=12)
        self.repeat_delay_entry.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)

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

        control_frame = ttk.LabelFrame(self, text="제어")
        control_frame.pack(fill=tk.X, padx=10, pady=5, expand=True, anchor=tk.S)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)

        self.start_button = ttk.Button(control_frame, text="시작 (F3)", command=self.macro.start)
        self.start_button.grid(row=0, column=0, sticky=tk.EW, padx=5, pady=5)
        self.stop_button = ttk.Button(control_frame, text="중지 (F4)", command=self.macro.stop, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)

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
            self.repeat_delay_var.set(s.get('repeat_delay', '1.0'))
            self.frenzy_mode_var.set(s.get('frenzy_mode', False))
            self.use_search_area_var.set(s.get('use_search_area', False))
            coords = s.get('search_area_coords', None)
            if coords and isinstance(coords, list) and len(coords) == 4:
                self.search_area_coords = tuple(coords)
                self.search_area_display_var.set(f"설정됨: X={coords[0]}, Y={coords[1]}, W={coords[2]}, H={coords[3]}")
            else:
                self.search_area_coords = None
                self.search_area_display_var.set("미설정")
            self.log("저장된 설정을 불러왔습니다.")
            self.app.log_event(f"✅ 이미지 설정 불러오기 완료")
        except Exception as e:
            self.app.log_event(f"⚠️ 설정 로드 실패: {e}")

    def save_settings(self):
        if not self.image_folder_path.get(): return
        s = {'click_interval': self.interval_var.get(), 'confidence_level': self.confidence_var.get(), 'repeat_delay': self.repeat_delay_var.get(), 'frenzy_mode': self.frenzy_mode_var.get(), 'use_search_area': self.use_search_area_var.get(), 'search_area_coords': self.search_area_coords}
        path = os.path.join(self.image_folder_path.get(), 'config.json')
        try:
            with open(path, 'w', encoding='utf-8') as f: json.dump(s, f, indent=4)
            self.app.log_event(f"💾 현재 설정을 폴더에 저장했습니다.")
        except Exception as e:
            self.app.log_event(f"⚠️ 설정 저장 실패: {e}")

    def update_ui_state(self, running):
        state = tk.DISABLED if running else tk.NORMAL
        self.start_button.config(state=state)
        self.stop_button.config(state=tk.NORMAL if running else tk.DISABLED)
        for widget in [self.folder_button, self.confidence_entry, self.frenzy_mode_check, self.use_search_area_check, self.set_area_button, self.interval_entry, self.repeat_delay_entry]:
            widget.config(state=state)

class RecordingMacroTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.macro = RecordingMacro(self)
        self.repeat_delay_var = tk.StringVar(value="1.0")
        self.new_recording_counter = 1
        self.playlist_data = {}
        self._create_widgets()

    def log(self, message):
        self.app.log(f"[체인] {message}")

    def _create_widgets(self):
        top_frame = ttk.LabelFrame(self, text="작업 관리")
        top_frame.pack(fill=tk.X, padx=10, pady=(10,5))
        top_frame.columnconfigure((0, 1, 2), weight=1)

        self.record_start_button = ttk.Button(top_frame, text="녹화 시작 (F1)", command=self.macro.start_recording)
        self.record_start_button.grid(row=0, column=0, sticky=tk.EW, padx=5, pady=5)
        self.record_stop_button = ttk.Button(top_frame, text="녹화 중지 (F2)", command=self.macro.stop_recording, state=tk.DISABLED)
        self.record_stop_button.grid(row=1, column=0, sticky=tk.EW, padx=5, pady=5)
        
        self.play_start_button = ttk.Button(top_frame, text="재생 시작 (F3)", command=self.start_macro_chain)
        self.play_start_button.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.play_stop_button = ttk.Button(top_frame, text="재생 중지 (F4)", command=self.macro.stop_playback, state=tk.DISABLED)
        self.play_stop_button.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)

        self.load_chain_button = ttk.Button(top_frame, text="체인 불러오기", command=self.load_chain)
        self.load_chain_button.grid(row=0, column=2, sticky=tk.EW, padx=5, pady=5)
        self.save_chain_button = ttk.Button(top_frame, text="체인 저장", command=self.save_chain)
        self.save_chain_button.grid(row=1, column=2, sticky=tk.EW, padx=5, pady=5)
        
        playlist_frame = ttk.LabelFrame(self, text="매크로 체인 (재생 목록)")
        playlist_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        playlist_frame.columnconfigure(0, weight=1)
        playlist_frame.rowconfigure(0, weight=1)

        list_container = ttk.Frame(playlist_frame)
        list_container.grid(row=0, column=0, sticky='nsew', pady=5, padx=5)
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        
        columns = ("#1", "#2")
        self.macro_tree = ttk.Treeview(list_container, columns=columns, show="headings", selectmode="browse")
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
        
        ttk.Label(bottom_frame, text="전체 반복 대기(초):").pack(side=tk.LEFT)
        self.repeat_delay_entry = ttk.Entry(bottom_frame, textvariable=self.repeat_delay_var, width=8)
        self.repeat_delay_entry.pack(side=tk.LEFT, padx=5)

    def on_tree_select(self, event):
        selected_item = self.macro_tree.selection()
        if not selected_item:
            self.save_button.config(state=tk.DISABLED)
            return
        
        item_id = selected_item[0]
        item_data = self.playlist_data.get(item_id)
        if item_data and (item_data['type'] == 'image' or item_data['type'] == 'image_wait'):
            self.save_button.config(state=tk.DISABLED)
        else:
            self.save_button.config(state=tk.NORMAL)

    def on_tree_double_click(self, event):
        if self.macro.is_playing or self.macro.is_recording: return
        region = self.macro_tree.identify("region", event.x, event.y)
        if region != "cell": return

        column = self.macro_tree.identify_column(event.x)
        selected_item = self.macro_tree.focus()
        if not selected_item: return

        item_data = self.playlist_data.get(selected_item)
        if not item_data: return

        if column == "#2":
            self.edit_tree_cell(selected_item, column)
        elif column == "#1" and item_data['type'] != 'file':
            self.edit_tree_cell(selected_item, column)

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
            if column == "#1":
                self.playlist_data[item]['display_name'] = new_value
            entry_edit.destroy()

        entry_edit.bind("<FocusOut>", lambda e: entry_edit.destroy())
        entry_edit.bind("<Return>", on_enter_pressed)
        
    def start_macro_chain(self):
        playlist = []
        for item_id in self.macro_tree.get_children():
            item_data = self.playlist_data.get(item_id)
            if item_data:
                item_info = item_data.copy()
                item_info['delay'] = self.macro_tree.set(item_id, "#2")
                item_info['display_name'] = self.macro_tree.set(item_id, "#1")
                playlist.append(item_info)
            
        if not playlist:
            self.log("⚠️ 재생 목록에 매크로를 추가해주세요.")
            return
        self.macro.start_playback(playlist)

    def add_file_macro_to_list(self):
        files = filedialog.askopenfilenames(title="녹화 파일 추가", filetypes=[("JSON files", "*.json")])
        if files:
            for file_path in files:
                display_name = os.path.basename(file_path)
                item_id = self.macro_tree.insert("", tk.END, values=(display_name, "1.0"))
                self.playlist_data[item_id] = {'type': 'file', 'data': file_path, 'display_name': display_name}
            self.log(f"✅ {len(files)}개 녹화 매크로를 추가했습니다.")

    def add_wait_image_macro_to_list(self):
        file = filedialog.askopenfilename(title="이미지(대기) 파일 선택", filetypes=[("PNG files", "*.png")])
        if file:
            display_name = f"[이미지 대기] {os.path.basename(file)}"
            item_id = self.macro_tree.insert("", tk.END, values=(display_name, "1.0"), tags=('image_wait_macro',))
            self.macro_tree.tag_configure('image_wait_macro', foreground='#E69138') # 주황색
            self.playlist_data[item_id] = {'type': 'image_wait', 'data': file, 'display_name': display_name}
            self.log(f"✅ 이미지(대기) '{os.path.basename(file)}'를 추가했습니다.")

    def add_memory_macro_to_list(self, actions):
        display_name = f"새 녹화 {self.new_recording_counter}"
        self.new_recording_counter += 1
        item_id = self.macro_tree.insert("", tk.END, values=(display_name, "1.0"), tags=('memory_macro',))
        self.macro_tree.tag_configure('memory_macro', foreground='blue')
        self.playlist_data[item_id] = {'type': 'memory', 'data': actions, 'display_name': display_name}
        self.log(f"✅ '{display_name}'를 재생 목록에 추가했습니다.")

    def save_selected_macro(self):
        selected_item = self.macro_tree.selection()
        if not selected_item:
            self.log("⚠️ 저장할 항목을 목록에서 선택하세요.")
            return
        
        item_id = selected_item[0]
        item_data = self.playlist_data.get(item_id)
        if not item_data or item_data['type'] in ['image', 'image_wait']: return

        actions_to_save = item_data.get('data') if item_data['type'] == 'memory' else []
        if item_data['type'] == 'file':
            try:
                with open(item_data['data'], 'r', encoding='utf-8') as f:
                    actions_to_save = json.load(f).get('actions', [])
            except Exception as e:
                self.log(f"🔥 파일을 읽는 중 오류 발생: {e}")
                return
        
        if not actions_to_save:
            self.log("⚠️ 저장할 동작이 없습니다.")
            return

        file_path = filedialog.asksaveasfilename(
            initialfile=self.macro_tree.set(item_id, "#1").replace(".json", "") + ".json",
            defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not file_path: return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({'actions': actions_to_save}, f, indent=4)
            
            new_display_name = os.path.basename(file_path)
            self.macro_tree.set(item_id, "#1", new_display_name)
            self.macro_tree.item(item_id, tags=())
            self.playlist_data[item_id] = {'type': 'file', 'data': file_path, 'display_name': new_display_name}
            self.app.log_event(f"💾 매크로 저장 완료: '{new_display_name}'")
        except Exception as e:
            self.app.log_event(f"🔥 파일 저장 실패: {e}")
            
    def save_chain(self):
        if not self.playlist_data:
            self.log("⚠️ 저장할 체인이 없습니다.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="매크로 체인 저장",
            defaultextension=".pchain", 
            filetypes=[("Pucro Chain files", "*.pchain"), ("All files", "*.*")])
        if not file_path: return

        chain_content = {
            'settings': {'repeat_delay': self.repeat_delay_var.get()},
            'playlist': []
        }
        for item_id in self.macro_tree.get_children():
            item_data = self.playlist_data.get(item_id)
            if item_data:
                chain_item = {
                    'type': item_data['type'],
                    'data': item_data['data'],
                    'display_name': self.macro_tree.set(item_id, "#1"),
                    'delay': self.macro_tree.set(item_id, "#2")
                }
                chain_content['playlist'].append(chain_item)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(chain_content, f, indent=4, ensure_ascii=False)
            self.app.log_event(f"💾 체인 저장 완료: '{os.path.basename(file_path)}'")
        except Exception as e:
            self.app.log_event(f"🔥 체인 저장 실패: {e}")

    def load_chain(self):
        file_path = filedialog.askopenfilename(
            title="매크로 체인 불러오기",
            filetypes=[("Pucro Chain files", "*.pchain"), ("All files", "*.*")])
        if not file_path: return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                chain_content = json.load(f)
            
            self.clear_macro_list()
            self.repeat_delay_var.set(chain_content.get('settings', {}).get('repeat_delay', '1.0'))

            for item in chain_content.get('playlist', []):
                item_type = item.get('type')
                item_data = item.get('data')
                display_name = item.get('display_name')
                delay = item.get('delay', '1.0')
                
                tags = ()
                if item_type == 'memory':
                    tags = ('memory_macro',)
                elif item_type == 'image_wait':
                    tags = ('image_wait_macro',)
                
                item_id = self.macro_tree.insert("", tk.END, values=(display_name, delay), tags=tags)
                self.playlist_data[item_id] = {'type': item_type, 'data': item_data, 'display_name': display_name}

            self.macro_tree.tag_configure('memory_macro', foreground='blue')
            self.macro_tree.tag_configure('image_wait_macro', foreground='#E69138')
            self.app.log_event(f"💾 체인 불러오기 완료: '{os.path.basename(file_path)}'")

        except Exception as e:
            self.app.log_event(f"🔥 체인 불러오기 실패: {e}")

    def remove_selected_macro(self):
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.log("⚠️ 목록에서 제거할 항목을 선택하세요.")
            return
        for item in selected_items:
            if item in self.playlist_data: del self.playlist_data[item]
            self.macro_tree.delete(item)
        self.log("선택한 항목을 재생 목록에서 제거했습니다.")

    def clear_macro_list(self):
        for item in self.macro_tree.get_children(): self.macro_tree.delete(item)
        self.playlist_data.clear()
        self.log("재생 목록을 모두 비웠습니다.")

    def move_macro_up(self):
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.log("⚠️ 이동할 항목을 선택하세요.")
            return
        for item in selected_items:
            self.macro_tree.move(item, self.macro_tree.parent(item), self.macro_tree.index(item) - 1)

    def move_macro_down(self):
        selected_items = self.macro_tree.selection()
        if not selected_items:
            self.log("⚠️ 이동할 항목을 선택하세요.")
            return
        for item in reversed(selected_items):
            self.macro_tree.move(item, self.macro_tree.parent(item), self.macro_tree.index(item) + 1)

    def update_ui_state(self, recording=None, playing=None):
        is_busy = (recording is not None and recording) or (playing is not None and playing) or self.macro.is_playing or self.macro.is_recording
        state = tk.DISABLED if is_busy else tk.NORMAL

        self.record_start_button.config(state=state)
        self.play_start_button.config(state=state)
        self.record_stop_button.config(state=tk.NORMAL if self.macro.is_recording else tk.DISABLED)
        self.play_stop_button.config(state=tk.NORMAL if self.macro.is_playing else tk.DISABLED)
        
        for btn in [self.add_file_button, self.add_wait_image_button, self.remove_button, self.up_button, self.down_button, self.clear_button, self.save_chain_button, self.load_chain_button]:
            btn.config(state=state)
        self.repeat_delay_entry.config(state=state)
        self.on_tree_select(None)

        if self.macro.is_recording: self.app.update_status("녹화 중...")
        elif self.macro.is_playing: self.app.update_status("재생 중...")
        else: self.app.update_status("준비")


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
        
        notes_text_widget.insert(tk.END, "푸크로 v2.5\n", "title")
        notes_text_widget.insert(tk.END, "주요 변경사항\n", "subtitle")
        notes_text_widget.insert(tk.END, "• 🔧 [안정성] 매크로 체인에서 불안정하게 동작할 수 있는 '이미지(반복)' 추가 기능을 제거했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🔧 [단순화] 패키징 편의성을 위해 프로그램 아이콘 설정 기능을 제거했습니다.\n", "item")

        notes_text_widget.insert(tk.END, "\n푸크로 v2.4\n", "title")
        notes_text_widget.insert(tk.END, "주요 변경사항\n", "subtitle")
        notes_text_widget.insert(tk.END, "• ✨ [핵심 기능] 매크로 체인에 '이미지 대기' 작업을 추가했습니다.\n", "item")
        
        notes_text_widget.insert(tk.END, "\n푸크로 v2.3\n", "title")
        notes_text_widget.insert(tk.END, "주요 변경사항\n", "subtitle")
        notes_text_widget.insert(tk.END, "• 🐞 [버그 수정] 파일 경로에 한글이 포함된 경우 이미지 매크로가 작동하지 않던 문제를 해결했습니다.\n", "item")

        notes_text_widget.config(state=tk.DISABLED)

class InfoTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self._create_widgets()

    def _create_widgets(self):
        info_frame = ttk.LabelFrame(self, text="안내 사항")
        info_frame.pack(fill=tk.BOTH, expand=True)
        title_label = ttk.Label(info_frame, text="⚙️ 관리자 권한으로 실행 안내", font=("", 11, "bold"))
        title_label.pack(anchor=tk.W, padx=10, pady=(10, 5))
        desc_text = "게임 내에서 매크로가 정상적으로 클릭하려면, 프로그램을 '관리자 권한'으로 실행해야 합니다."
        desc_label = ttk.Label(info_frame, text=desc_text, wraplength=450)
        desc_label.pack(anchor=tk.W, padx=10, pady=5, fill=tk.X)
        ttk.Separator(info_frame, orient='horizontal').pack(fill='x', padx=10, pady=10)
        how_to_title = ttk.Label(info_frame, text="💡 영구 설정 방법")
        how_to_title.pack(anchor=tk.W, padx=10, pady=(0, 5))
        how_to_text = ("1. 프로그램 파일(.exe 또는 .py)을 마우스 오른쪽 버튼으로 클릭\n"
                       "2. '속성' > '호환성' 탭으로 이동\n"
                       "3. '관리자 권한으로 이 프로그램 실행' 옵션을 체크하고 '확인'\n\n"
                       "이렇게 설정하면, 앞으로 프로그램을 켤 때마다 자동으로 관리자 권한을 요청합니다.")
        how_to_label = ttk.Label(info_frame, text=how_to_text, justify=tk.LEFT)
        how_to_label.pack(anchor=tk.W, padx=10, pady=5)

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

# --- 4. 메인 애플리케이션 클래스 ---
class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("푸크로 V2.5")
        self.root.geometry("550x720")

        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            print("'clam' 테마를 찾을 수 없습니다. 기본 테마로 실행합니다.")
        
        self.style.configure("Treeview.Heading", font=(None, 10, 'bold'))
        self.style.configure("TButton", padding=5)
        self.style.configure("TMenubutton", padding=5)

        self.hotkey_listener = None
        self._create_widgets()
        self._setup_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        tab_image = ttk.Frame(self.notebook)
        tab_record = ttk.Frame(self.notebook)
        tab_patch = ttk.Frame(self.notebook)
        tab_info = ttk.Frame(self.notebook)

        self.notebook.add(tab_image, text="  이미지 매크로  ")
        self.notebook.add(tab_record, text="  매크로 체인  ")
        self.notebook.add(tab_patch, text="  패치노트  ")
        self.notebook.add(tab_info, text="  도움말  ")

        self.image_tab = ImageMacroTab(tab_image, self)
        self.image_tab.pack(fill=tk.BOTH, expand=True)
        self.recording_tab = RecordingMacroTab(tab_record, self)
        self.recording_tab.pack(fill=tk.BOTH, expand=True)
        self.patch_notes_tab = PatchNotesTab(tab_patch)
        self.patch_notes_tab.pack(fill=tk.BOTH, expand=True)
        self.info_tab = InfoTab(tab_info)
        self.info_tab.pack(fill=tk.BOTH, expand=True)

        log_container = ttk.Frame(main_frame)
        log_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5,0))
        log_container.columnconfigure(0, weight=1)
        log_container.rowconfigure(1, weight=1)

        event_log_frame = ttk.LabelFrame(log_container, text="이벤트 로그")
        event_log_frame.grid(row=0, column=0, sticky='ew')
        event_log_frame.columnconfigure(0, weight=1)
        self.event_log_text = scrolledtext.ScrolledText(event_log_frame, wrap=tk.WORD, height=4, state=tk.DISABLED, bd=0)
        self.event_log_text.pack(fill=tk.X, expand=True, padx=5, pady=5)

        run_log_frame = ttk.LabelFrame(log_container, text="실행 로그")
        run_log_frame.grid(row=1, column=0, sticky='nsew', pady=(5,0))
        run_log_frame.columnconfigure(0, weight=1)
        run_log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(run_log_frame, wrap=tk.WORD, state=tk.DISABLED, bd=0)
        self.log_text.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        
        ttk.Button(run_log_frame, text="로그 지우기", command=self.clear_log).grid(row=1, column=0, sticky='e', padx=5, pady=(0,5))
        
        self.log("프로그램 준비 완료. 사용할 탭을 선택하고 시작하세요.")

        self.status_var = tk.StringVar(value="준비")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _setup_hotkeys(self):
        try:
            self.hotkey_listener = keyboard.Listener(on_press=self._on_key_press)
            self.hotkey_listener.start()
            self.log("전역 단축키 활성화. (활성 탭에 따라 동작)")
        except Exception as e:
            self.log(f"🔥 단축키 설정 실패: {e}")
            self.log("ℹ️ 관리자 권한으로 실행하거나 접근성 권한을 확인하세요.")

    def _on_key_press(self, key):
        try:
            if self.recording_tab.macro.is_recording:
                if key == keyboard.Key.f2: self.root.after(0, self.recording_tab.record_stop_button.invoke)
                return

            current_tab_index = self.notebook.index(self.notebook.select())
            if current_tab_index == 0:
                if key == keyboard.Key.f3: self.root.after(0, self.image_tab.start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.image_tab.stop_button.invoke)
                elif key == keyboard.Key.f9: self.root.after(0, self.image_tab.start_defining_area)
            elif current_tab_index == 1:
                if key == keyboard.Key.f1: self.root.after(0, self.recording_tab.record_start_button.invoke)
                elif key == keyboard.Key.f2: self.root.after(0, self.recording_tab.record_stop_button.invoke)
                elif key == keyboard.Key.f3: self.root.after(0, self.recording_tab.play_start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.recording_tab.play_stop_button.invoke)
        except Exception: pass

    def _on_closing(self):
        if self.hotkey_listener and self.hotkey_listener.is_alive():
            self.hotkey_listener.stop()
        self.root.destroy()

    def log(self, message):
        self.root.after(0, self._log_update, self.log_text, message)

    def log_event(self, message):
        self.root.after(0, self._log_update, self.event_log_text, message)

    def _log_update(self, text_widget, message):
        text_widget.config(state=tk.NORMAL)
        text_widget.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        text_widget.see(tk.END)
        text_widget.config(state=tk.DISABLED)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.log("로그 창을 초기화했습니다.")

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
