import threading
import time
import os
import pyautogui
from pynput import mouse, keyboard
from constants import ActionType, MacroType, RepeatMode
from utils import execute_image_scan
from executor import MacroExecutor

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

        # 데몬 스레드로 설정하여 메인 프로그램 종료 시 함께 종료되도록 함
        self.macro_thread = threading.Thread(target=self.run_macro, args=(settings,), daemon=True)
        self.macro_thread.start()
        self.c['update_ui'](running=True)

    def stop(self):
        if not self.is_running: return
        self.stop_event.set()
        self.pause_event.set() # 일시정지 상태에서 멈출 수 있도록 깨움
        self.is_running = False
        self.c['log']("중지 요청 중...")

    def pause_or_resume(self):
        if not self.is_running: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.clear()
            self.c['log']("⏸️ 이미지 매크로 일시정지.")
            self.c['update_status']("일시정지")
        else:
            self.pause_event.set()
            self.c['log']("▶️ 이미지 매크로 재개.")
            self.c['update_status']("실행 중")
        self.c['update_ui'](paused=self.is_paused)

    def run_macro(self, settings):
        self.c['log']("🚀 이미지 매크로 시작")
        self.c['update_status']("실행 중")
        start_time = time.time()
        loop_count = 0

        try:
            while not self.stop_event.is_set():
                # 반복 조건 체크
                if settings['repeat_mode'] == RepeatMode.COUNT and loop_count >= settings['repeat_value']:
                    self.c['log'](f"👍 {loop_count}회 반복 완료.")
                    break
                if settings['repeat_mode'] == RepeatMode.DURATION and (time.time() - start_time) / 60 >= settings['repeat_value']:
                    self.c['log'](f"👍 {settings['repeat_value']}분 실행 완료.")
                    break

                # 일시정지 대기
                self.pause_event.wait()
                if self.stop_event.is_set(): break

                # 이미지 스캔 실행
                execute_image_scan(self.c['log'], settings['image_folder'], self.stop_event, self.pause_event)

                if self.stop_event.is_set(): break

                loop_count += 1

                # 반복 딜레이 (중지 체크 포함)
                delay = settings['repeat_delay']
                if delay > 0:
                    self.c['log'](f"⏳ {delay}초 대기...")
                    self.stop_event.wait(timeout=delay)

        except Exception as e:
            self.c['log'](f"🔥 치명적 오류 발생: {e}")
        finally:
            # 안전하게 상태 초기화
            self.is_running = False
            self.is_paused = False
            self.stop_event.clear()
            self.c['update_ui'](running=False, paused=False)
            self.c['log']("🛑 이미지 매크로 종료됨.")
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
        if self.is_recording: return

        # 기존 리스너가 혹시 살아있다면 정리
        self._stop_listeners()

        self.is_recording = True
        self.is_mouse_down = False
        self.recorded_actions = []
        self.last_action_time = time.time()

        try:
            # Listener 생성 및 시작
            self.mouse_listener = mouse.Listener(on_click=self._on_click, on_move=self._on_move)
            self.keyboard_listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
            self.mouse_listener.start()
            self.keyboard_listener.start()

            self.c['update_ui'](recording=True)
            self.c['log']("🔴 녹화 시작 (ESC나 F2로 중지 가능)")
        except Exception as e:
            self.c['log'](f"🔥 녹화 시작 실패: {e}")
            self.stop_recording()

    def stop_recording(self):
        if not self.is_recording: return

        self._stop_listeners()
        self.is_recording = False

        self.c['update_ui'](recording=False)
        self.c['log'](f"⏹️ 녹화 완료: {len(self.recorded_actions)}개 동작.")

        if self.recorded_actions:
            self.c['add_macro_to_list'](self.recorded_actions)
            # self.recorded_actions = [] # 추가 후 초기화하지 않고 유지 (실수 방지)

    def _stop_listeners(self):
        """리스너를 안전하게 중지합니다."""
        if self.mouse_listener:
            if self.mouse_listener.is_alive():
                self.mouse_listener.stop()
            self.mouse_listener = None
        if self.keyboard_listener:
            if self.keyboard_listener.is_alive():
                self.keyboard_listener.stop()
            self.keyboard_listener = None

    def _get_key_str(self, key):
        if hasattr(key, 'char') and key.char: return key.char
        elif hasattr(key, 'name'): return key.name.lower()
        return str(key).replace("'", "")

    def _on_press(self, key):
        if not self.is_recording: return
        key_str = self._get_key_str(key)
        if key_str:
            cur_time = time.time()
            self.recorded_actions.append({
                'type': ActionType.KEY_DOWN.value,
                'key': key_str,
                'delay': cur_time - self.last_action_time
            })
            self.last_action_time = cur_time

    def _on_release(self, key):
        if not self.is_recording: return
        # 녹화 중지 키 (F2, ESC) 처리
        if key == keyboard.Key.f2 or key == keyboard.Key.esc:
            # 이 키는 기록하지 않고 녹화 중지 호출은 UI 스레드나 메인 루프에서 처리되도록 함
            return

        key_str = self._get_key_str(key)
        if key_str:
            cur_time = time.time()
            self.recorded_actions.append({
                'type': ActionType.KEY_UP.value,
                'key': key_str,
                'delay': cur_time - self.last_action_time
            })
            self.last_action_time = cur_time

    def _on_click(self, x, y, button, pressed):
        if not self.is_recording: return
        self.is_mouse_down = pressed
        cur_time = time.time()
        action_type = ActionType.MOUSE_DOWN.value if pressed else ActionType.MOUSE_UP.value
        btn_str = str(button).replace('Button.', '')
        self.recorded_actions.append({
            'type': action_type,
            'pos': (x, y),
            'button': btn_str,
            'delay': cur_time - self.last_action_time
        })
        self.last_action_time = cur_time

    def _on_move(self, x, y):
        # 마우스 이동은 드래그(클릭 상태) 일 때만 기록하여 데이터 양을 줄임
        if self.is_recording and self.is_mouse_down:
            cur_time = time.time()
            # 너무 잦은 기록 방지 (0.02초 간격)
            if cur_time - self.last_action_time < 0.02: return

            self.recorded_actions.append({
                'type': ActionType.MOVE.value,
                'pos': (x, y),
                'delay': cur_time - self.last_action_time
            })
            self.last_action_time = cur_time

    def start_playback(self, settings):
        if self.is_playing: return
        if not settings['playlist']:
            self.c['log']("⚠️ 재생할 목록이 없습니다.")
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
        self.stop_event.set()
        self.pause_event.set() # 일시정지 해제하여 루프 탈출
        self.is_playing = False
        self.c['log']("중지 요청 중...")

    def pause_or_resume_playback(self):
        if not self.is_playing: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.clear()
            self.c['log']("⏸️ 일시정지")
            self.c['update_status']("일시정지")
        else:
            self.pause_event.set()
            self.c['log']("▶️ 재개")
            self.c['update_status']("재생 중")
        self.c['update_ui'](paused=self.is_paused)

    def run_playback(self, settings):
        self.c['log']("🚀 매크로 재생 시작")
        self.c['update_status']("재생 중")

        # [수정] 기존 PAUSE 값 저장 및 복원 (다른 로직 영향 방지)
        original_pause = pyautogui.PAUSE
        pyautogui.PAUSE = 0.01

        start_time = time.time()
        loop_count = 0

        try:
            while not self.stop_event.is_set():
                # 반복 조건 확인
                if settings['repeat_mode'] == RepeatMode.COUNT and loop_count >= settings['repeat_value']:
                    self.c['log']("👍 지정 횟수 완료.")
                    break
                if settings['repeat_mode'] == RepeatMode.DURATION and (time.time() - start_time) / 60 >= settings['repeat_value']:
                    self.c['log']("👍 지정 시간 완료.")
                    break

                # 재생 목록 실행
                for item_info in settings['playlist']:
                    if self.stop_event.is_set(): break

                    # 매크로 실행 위임 (성공 여부 반환)
                    success = MacroExecutor.execute_macro_item(
                        item_info, self.c, self.stop_event, self.pause_event,
                        settings['playback_speed'], settings['image_timeout'],
                        settings.get('app'), settings.get('tree')
                    )

                    if not success: # 중지 요청이나 오류로 실패 시
                        self.stop_event.set()
                        break

                if self.stop_event.is_set(): break

                loop_count += 1
                delay = settings['repeat_delay']
                if delay > 0:
                    self.c['log'](f"⏳ {delay}초 대기...")
                    self.stop_event.wait(timeout=delay)

        except Exception as e:
            self.c['log'](f"🔥 재생 중 오류: {e}")
        finally:
            # [수정] PAUSE 값 원상 복구
            pyautogui.PAUSE = original_pause

            self.is_playing = False
            self.is_paused = False
            self.stop_event.clear()
            self.c['update_ui'](playing=False, paused=False)
            self.c['log']("🛑 재생 종료")
            self.c['update_status']("준비")

    def test_run_single_item(self, settings):
        if self.is_playing:
            self.c['log']("⚠️ 이미 실행 중입니다.")
            return
        self.is_playing = True
        self.stop_event.clear()
        self.pause_event.set()

        threading.Thread(target=self._run_single, args=(settings,), daemon=True).start()
        self.c['update_ui'](playing=True)

    def _run_single(self, settings):
        self.c['log'](f"🧪 테스트: '{settings['playlist'][0]['display_name']}'")

        # [수정] 테스트 실행 시에도 PAUSE 조절
        original_pause = pyautogui.PAUSE
        pyautogui.PAUSE = 0.01

        try:
            MacroExecutor.execute_macro_item(
                settings['playlist'][0], self.c, self.stop_event, self.pause_event,
                settings['playback_speed'], settings['image_timeout'],
                settings.get('app'), settings.get('tree')
            )
        except Exception as e:
            self.c['log'](f"🔥 테스트 오류: {e}")
        finally:
            pyautogui.PAUSE = original_pause
            self.is_playing = False
            self.c['update_ui'](playing=False)
            self.c['log']("🧪 테스트 완료")
            self.c['update_status']("준비")


# --- 3. 매크로 그룹 로직 클래스 ---
class ChainGroupMacro:
    def __init__(self, callbacks):
        self.c = callbacks
        self.is_playing = False
        self.is_paused = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

    def start_playback(self, settings):
        if self.is_playing: return
        if not settings['chain_playlist']:
            self.c['log']("⚠️ 그룹 목록이 비어있습니다.")
            return

        self.is_playing = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()

        threading.Thread(target=self.run_playback, args=(settings,), daemon=True).start()
        self.c['update_ui'](playing=True)

    def stop_playback(self):
        if not self.is_playing: return
        self.stop_event.set()
        self.pause_event.set()
        self.is_playing = False
        self.c['log']("그룹 중지 요청...")

    def pause_or_resume_playback(self):
        if not self.is_playing: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.clear()
            self.c['log']("⏸️ 그룹 일시정지")
            self.c['update_status']("일시정지")
        else:
            self.pause_event.set()
            self.c['log']("▶️ 그룹 재개")
            self.c['update_status']("실행 중")
        self.c['update_ui'](paused=self.is_paused)

    def run_playback(self, settings):
        self.c['log']("🚀 매크로 그룹 재생 시작")
        self.c['update_status']("그룹 실행 중")

        # [수정] PAUSE 값 안전 처리
        original_pause = pyautogui.PAUSE
        pyautogui.PAUSE = 0.01

        start_time = time.time()
        loop_count = 0

        try:
            while not self.stop_event.is_set():
                if settings['repeat_mode'] == RepeatMode.COUNT and loop_count >= settings['repeat_value']:
                    self.c['log']("👍 그룹 지정 횟수 완료.")
                    break
                if settings['repeat_mode'] == RepeatMode.DURATION and (time.time() - start_time) / 60 >= settings['repeat_value']:
                    self.c['log']("👍 그룹 지정 시간 완료.")
                    break

                # 그룹 내 체인 순차 실행
                for chain_index, chain_info in enumerate(settings['chain_playlist']):
                    if self.stop_event.is_set(): break
                    self.pause_event.wait()

                    chain_path = chain_info['path']
                    chain_repeats = int(chain_info['repeats'])
                    chain_delay = float(chain_info['delay_after'])

                    self.c['log'](f"📂 그룹 ({chain_index+1}/{len(settings['chain_playlist'])}) '{os.path.basename(chain_path)}' 시작 (x{chain_repeats})")

                    # 체인 파일 로드
                    macro_playlist = self.c['load_macros_from_chain'](chain_path)
                    if not macro_playlist:
                        self.c['log'](f"⚠️ 체인 로드 실패: {os.path.basename(chain_path)}")
                        self.stop_event.set()
                        break

                    # 해당 체인 반복
                    for i in range(chain_repeats):
                        if self.stop_event.is_set(): break
                        self.pause_event.wait()

                        # 체인 내 아이템 실행
                        for macro_item in macro_playlist:
                            if self.stop_event.is_set(): break
                            success = MacroExecutor.execute_macro_item(
                                macro_item, self.c, self.stop_event, self.pause_event,
                                settings['playback_speed'], settings['image_timeout'],
                                settings.get('app'), settings.get('tree')
                            )
                            if not success:
                                self.stop_event.set()
                                break

                        if self.stop_event.is_set(): break

                    if not self.stop_event.is_set() and chain_delay > 0:
                        self.c['log'](f"⏳ 체인 간 대기 {chain_delay}초...")
                        self.stop_event.wait(timeout=chain_delay)

                if self.stop_event.is_set(): break

                loop_count += 1
                delay = settings['repeat_delay']
                if delay > 0:
                    self.c['log'](f"⏳ 그룹 반복 대기 {delay}초...")
                    self.stop_event.wait(timeout=delay)

        except Exception as e:
            self.c['log'](f"🔥 그룹 실행 중 오류: {e}")
        finally:
            # [수정] PAUSE 복원
            pyautogui.PAUSE = original_pause

            self.is_playing = False
            self.is_paused = False
            self.stop_event.clear()
            self.c['update_ui'](playing=False, paused=False)
            self.c['log']("🛑 그룹 재생 종료")
            self.c['update_status']("준비")