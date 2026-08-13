import threading
import time
import os
import pyautogui
from pynput import mouse, keyboard
from constants import ActionType, MacroType, RepeatMode
from utils import execute_image_scan, refresh_screen_info, reset_image_search_errors
from executor import MacroExecutor, InputTracker, EXECUTION_LOCK

# --- 1. 이미지 매크로 로직 클래스 ---
class AutoClickerMacro:
    # 래퍼가 락 반납 후 보낼 최종 UI 상태
    _FINAL_UI = {'running': False, 'paused': False}

    def __init__(self, callbacks):
        self.c = callbacks
        self.is_running = False
        self.is_paused = False
        self.macro_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self._exec_token = None

    def start(self, settings):
        if self.is_running:
            self.c['log']("⚠️ 이미 이미지 매크로가 실행 중입니다.")
            return
        if not settings['image_folder']:
            self.c['log']("⚠️ 먼저 이미지 폴더를 선택해주세요.")
            return

        # 마우스·키보드를 공유하므로 다른 작업이 실행 중이면 시작하지 않는다.
        self._exec_token = EXECUTION_LOCK.acquire("이미지 매크로")
        if self._exec_token is None:
            self.c['log'](f"⚠️ '{EXECUTION_LOCK.current_label()}'이(가) 실행 중입니다. 먼저 중지해주세요.")
            return

        # 토큰 획득 이후의 시작 절차 전체(UI 갱신 포함)를 실패 정리로 감싼다.
        try:
            self.is_running = True
            self.is_paused = False
            self.stop_event.clear()
            self.pause_event.set()

            # 실행 중 상태를 스레드 시작 전에 확정한다.
            # 스레드가 곧바로 끝나면 종료 갱신보다 늦게 큐에 들어가 화면이 실행 중으로 남는다.
            self.c['update_ui'](running=True)

            # 데몬 스레드로 설정하여 메인 프로그램 종료 시 함께 종료되도록 함
            self.macro_thread = threading.Thread(target=self.run_macro, args=(settings,), daemon=True)
            self.macro_thread.start()
        except Exception as e:
            self._abort_start(f"🔥 이미지 매크로 시작 실패: {e}")
            return

    def _abort_start(self, message):
        """시작 도중 실패했을 때 상태·실행 권한·화면을 모두 되돌립니다.

        UI 갱신이나 스레드 시작 어느 쪽이 실패해도 작업 스레드의 최외곽 finally가
        돌지 않으므로, 여기서 토큰과 PAUSE(락이 함께 복원)를 직접 반납해야 한다.
        """
        self.is_running = False
        self.is_paused = False
        EXECUTION_LOCK.release(self._exec_token)
        self._exec_token = None
        for call in (lambda: self.c['log'](message),
                     lambda: self.c['update_ui'](**self._FINAL_UI)):
            try:
                call()
            except Exception:
                pass

    def stop(self):
        if not self.is_running: return
        self.stop_event.set()
        self.pause_event.set() # 일시정지 상태에서 멈출 수 있도록 깨움
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
        """실행 권한 반납을 보장하는 래퍼.

        본문이 어느 지점에서 실패하더라도(초기화 중 예외 포함) 최외곽 finally에서
        토큰과 pyautogui.PAUSE를 반드시 복원한다. 그렇지 않으면 락이 잡힌 채 남아
        앱 전체에서 매크로를 다시 시작할 수 없게 된다.
        """
        token = self._exec_token
        try:
            self._run_macro_body(settings)
        finally:
            try:
                self.is_running = False
                self.is_paused = False
            finally:
                EXECUTION_LOCK.release(token)
                self._exec_token = None
                # 락 해제 이후 상태를 UI에 반영한다. (해제 전 갱신은 잠긴 상태로 남는다)
                try:
                    self.c['update_ui'](**self._FINAL_UI)
                except Exception:
                    pass

    def _run_macro_body(self, settings):
        self.c['log']("🚀 이미지 매크로 시작")
        self.c['update_status']("실행 중")

        # 모니터 구성이 바뀌었을 수 있으므로 좌표 판정 기준을 갱신하고,
        # 이전 실행에서 남은 오류 안내 기록을 초기화한다.
        refresh_screen_info()
        reset_image_search_errors()

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

class _RecordSession:
    """한 번의 녹화 세션.

    동작 목록과 타이밍을 **세션 자신이** 들고 있어, 중지·재시작이 겹쳐도
    이미 진입한 이전 세션 콜백이 새 세션의 목록에 기록할 수 없다.
    """
    __slots__ = ('actions', 'last_time', 'mouse_down', 'closed')

    def __init__(self):
        self.actions = []
        self.last_time = time.time()
        self.mouse_down = False
        self.closed = False


# --- 2. 녹화 매크로 로직 클래스 ---
class RecordingMacro:
    # 래퍼가 락 반납 후 보낼 최종 UI 상태
    _FINAL_UI = {'playing': False, 'paused': False}

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
        # 이 매크로의 실행이 누른 입력만 추적한다. (다른 탭 실행과 섞이지 않도록)
        self.input_tracker = InputTracker()
        self._exec_token = None
        self._record_token = None
        # 녹화 세션. 중지에 실패해 살아남은 이전 리스너의 콜백이
        # 다음 녹화에서 되살아나 같은 입력을 중복 기록하는 것을 막는다.
        self._record_session = None
        # 세션 확인과 기록을 원자적으로 처리한다.
        # (검사만 통과한 뒤 중지·재시작이 끼어들면 새 세션 목록이 오염된다)
        self._record_lock = threading.RLock()

    def start_recording(self):
        if self.is_recording: return

        # 재생 중에 녹화하면 재생된 입력이 그대로 기록되므로 함께 배제한다.
        self._record_token = EXECUTION_LOCK.acquire("녹화", adjust_pause=False)
        if self._record_token is None:
            self.c['log'](f"⚠️ '{EXECUTION_LOCK.current_label()}'이(가) 실행 중입니다. 먼저 중지해주세요.")
            return

        # 토큰을 얻은 뒤의 준비 과정 전체를 감싼다.
        # 리스너 정리·생성 어디서 실패해도 권한이 잠긴 채 남으면 안 된다.
        try:
            self._stop_listeners()   # 기존 리스너가 혹시 살아있다면 정리

            self.is_recording = True
            self.is_mouse_down = False

            # 이번 녹화 세션. 콜백은 자기 세션의 저장소에만 기록한다.
            session = _RecordSession()
            with self._record_lock:
                self._record_session = session
                self.recorded_actions = session.actions

            # Listener 생성 및 시작
            self.mouse_listener = mouse.Listener(
                on_click=lambda x, y, button, pressed: self._on_click(x, y, button, pressed, session),
                on_move=lambda x, y: self._on_move(x, y, session))
            self.keyboard_listener = keyboard.Listener(
                on_press=lambda key: self._on_press(key, session),
                on_release=lambda key: self._on_release(key, session))
            self.mouse_listener.start()
            self.keyboard_listener.start()

            # UI 갱신도 보호 구간 안에서 수행한다. 실패하면 아래에서 전부 되돌린다.
            self.c['update_ui'](recording=True)
            self.c['log']("🔴 녹화 시작 (ESC나 F2로 중지 가능)")
        except Exception as e:
            with self._record_lock:
                self.is_recording = False
                session = self._record_session
                if session is not None:
                    session.closed = True
                self._record_session = None   # 콜백을 먼저 무력화
            try:
                self._stop_listeners()   # 일부만 시작됐을 수 있으므로 되돌린다
            except Exception:
                pass
            EXECUTION_LOCK.release(self._record_token)
            self._record_token = None
            try:
                self.c['log'](f"🔥 녹화 시작 실패: {e}")
                self.c['update_ui'](recording=False)
            except Exception:
                pass
            return

    def stop_recording(self):
        if not self.is_recording:
            # 시작에 실패해 잡히지 않은 토큰이 남아 있을 수 있으므로 정리만 한다.
            EXECUTION_LOCK.release(self._record_token)
            self._record_token = None
            return

        # 리스너 정리가 실패하더라도 상태와 실행 권한은 반드시 되돌린다.
        surviving = []
        try:
            surviving = self._stop_listeners()
        except Exception as e:
            self.c['log'](f"⚠️ 녹화 리스너 정리 중 오류: {e}")
        finally:
            # 세션을 먼저 닫아, 이미 진입한 콜백도 기록을 남기지 못하게 한다.
            with self._record_lock:
                session = self._record_session
                if session is not None:
                    session.closed = True
                    self.recorded_actions = session.actions
                self._record_session = None
                self.is_recording = False
            EXECUTION_LOCK.release(self._record_token)
            self._record_token = None
            try:
                self.c['update_ui'](recording=False)
            except Exception:
                pass

        if surviving:
            self.c['log'](
                f"⚠️ 녹화 리스너({', '.join(surviving)})를 중지하지 못했습니다. "
                "입력은 더 이상 기록되지 않지만 문제가 계속되면 프로그램을 다시 시작해주세요."
            )
        self.c['log'](f"⏹️ 녹화 완료: {len(self.recorded_actions)}개 동작.")

        if self.recorded_actions:
            self.c['add_macro_to_list'](self.recorded_actions)
            # self.recorded_actions = [] # 추가 후 초기화하지 않고 유지 (실수 방지)

    def _is_active_session(self, session):
        """이 콜백이 현재 진행 중인 녹화 세션의 것인지 확인합니다."""
        with self._record_lock:
            return self._is_active_session_locked(session)

    def _is_active_session_locked(self, session):
        """_record_lock을 쥔 상태에서 세션 유효성을 판정합니다.

        세션 인자가 없으면 거부한다(fail-closed). 세션을 넘기지 않는 경로가
        생기면 조용히 격리를 우회하게 되므로 허용하지 않는다.
        """
        if session is None or getattr(session, 'closed', True):
            return False
        if not self.is_recording:
            return False
        return session is self._record_session

    def _stop_listeners(self):
        """리스너를 안전하게 중지합니다.

        한쪽 정리가 실패해도 다른 쪽은 반드시 중지되도록 서로 독립적으로 처리한다.
        중지에 실패해 살아남은 리스너는 참조를 유지해 추적 가능하게 두고 목록을 반환한다.
        (세션 토큰으로 콜백은 이미 무력화되므로 기록이 오염되지는 않는다)
        """
        surviving = []
        for attr in ('mouse_listener', 'keyboard_listener'):
            listener = getattr(self, attr, None)
            if listener is None:
                continue

            stopped = False
            for _ in range(2):   # 일시적 실패를 감안해 한 번 더 시도
                try:
                    if listener.is_alive():
                        listener.stop()
                    stopped = True
                    break
                except Exception:
                    pass

            try:
                alive = bool(listener.is_alive())
            except Exception:
                alive = not stopped

            if alive:
                surviving.append(attr)   # 참조 유지
            else:
                setattr(self, attr, None)
        return surviving

    def _get_key_str(self, key):
        if hasattr(key, 'char') and key.char: return key.char
        elif hasattr(key, 'name'): return key.name.lower()
        return str(key).replace("'", "")

    def _on_press(self, key, session=None):
        # 녹화 중지 키(F2, ESC)는 기록하지 않음 (키가 눌린 상태로 남는 문제 방지)
        if key in (keyboard.Key.f2, keyboard.Key.esc):
            return
        key_str = self._get_key_str(key)
        if not key_str:
            return
        with self._record_lock:
            if not self._is_active_session_locked(session): return
            cur_time = time.time()
            session.actions.append({
                'type': ActionType.KEY_DOWN.value,
                'key': key_str,
                'delay': cur_time - session.last_time
            })
            session.last_time = cur_time

    def _on_release(self, key, session=None):
        # 녹화 중지 키 (F2, ESC) 처리
        if key == keyboard.Key.f2 or key == keyboard.Key.esc:
            # 이 키는 기록하지 않고 녹화 중지 호출은 UI 스레드나 메인 루프에서 처리되도록 함
            return

        key_str = self._get_key_str(key)
        if not key_str:
            return
        with self._record_lock:
            if not self._is_active_session_locked(session): return
            cur_time = time.time()
            session.actions.append({
                'type': ActionType.KEY_UP.value,
                'key': key_str,
                'delay': cur_time - session.last_time
            })
            session.last_time = cur_time

    def _on_click(self, x, y, button, pressed, session=None):
        action_type = ActionType.MOUSE_DOWN.value if pressed else ActionType.MOUSE_UP.value
        btn_str = str(button).replace('Button.', '')
        with self._record_lock:
            if not self._is_active_session_locked(session): return
            session.mouse_down = pressed
            self.is_mouse_down = pressed
            cur_time = time.time()
            session.actions.append({
                'type': action_type,
                'pos': (x, y),
                'button': btn_str,
                'delay': cur_time - session.last_time
            })
            session.last_time = cur_time

    def _on_move(self, x, y, session=None):
        # 마우스 이동은 드래그(클릭 상태) 일 때만 기록하여 데이터 양을 줄임
        with self._record_lock:
            if not self._is_active_session_locked(session): return
            if not session.mouse_down: return

            cur_time = time.time()
            # 너무 잦은 기록 방지 (0.02초 간격)
            if cur_time - session.last_time < 0.02: return

            session.actions.append({
                'type': ActionType.MOVE.value,
                'pos': (x, y),
                'delay': cur_time - session.last_time
            })
            session.last_time = cur_time

    def start_playback(self, settings):
        if self.is_playing: return
        if not settings['playlist']:
            self.c['log']("⚠️ 재생할 목록이 없습니다.")
            return

        self._exec_token = EXECUTION_LOCK.acquire("체인 재생")
        if self._exec_token is None:
            self.c['log'](f"⚠️ '{EXECUTION_LOCK.current_label()}'이(가) 실행 중입니다. 먼저 중지해주세요.")
            return

        self.is_playing = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()

        # 토큰 획득 이후의 시작 절차 전체(UI 갱신 포함)를 실패 정리로 감싼다.
        try:
            # 실행 중 상태를 스레드 시작 전에 확정한다. (종료 갱신과의 순서 역전 방지)
            self.c['update_ui'](playing=True)

            self.playback_thread = threading.Thread(target=self.run_playback, args=(settings,), daemon=True)
            self.playback_thread.start()
        except Exception as e:
            self._abort_start(f"🔥 재생 시작 실패: {e}")
            return

    def _abort_start(self, message):
        """시작 도중 실패했을 때 상태·실행 권한·화면을 모두 되돌립니다.

        UI 갱신이나 스레드 시작 어느 쪽이 실패해도 작업 스레드의 최외곽 finally가
        돌지 않으므로, 여기서 토큰과 PAUSE(락이 함께 복원)를 직접 반납해야 한다.
        """
        self.is_playing = False
        self.is_paused = False
        EXECUTION_LOCK.release(self._exec_token)
        self._exec_token = None
        for call in (lambda: self.c['log'](message),
                     lambda: self.c['update_ui'](**self._FINAL_UI)):
            try:
                call()
            except Exception:
                pass

    def stop_playback(self):
        if not self.is_playing: return
        self.stop_event.set()
        self.pause_event.set() # 일시정지 해제하여 루프 탈출
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
        """실행 권한 반납을 보장하는 래퍼.

        본문이 어느 지점에서 실패하더라도(초기화 중 예외 포함) 최외곽 finally에서
        토큰과 pyautogui.PAUSE를 반드시 복원한다. 그렇지 않으면 락이 잡힌 채 남아
        앱 전체에서 매크로를 다시 시작할 수 없게 된다.
        """
        token = self._exec_token
        try:
            self._run_playback_body(settings)
        finally:
            try:
                self.is_playing = False
                self.is_paused = False
            finally:
                EXECUTION_LOCK.release(token)
                self._exec_token = None
                # 락 해제 이후 상태를 UI에 반영한다. (해제 전 갱신은 잠긴 상태로 남는다)
                try:
                    self.c['update_ui'](**self._FINAL_UI)
                except Exception:
                    pass

    def _run_playback_body(self, settings):
        self.c['log']("🚀 매크로 재생 시작")
        self.c['update_status']("재생 중")

        refresh_screen_info()
        reset_image_search_errors()

        # pyautogui.PAUSE는 EXECUTION_LOCK이 저장·복원한다.
        # (여기서 직접 다루면 실행이 겹칠 때 값이 어긋난다)

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
                        settings.get('app'), settings.get('tree'),
                        settings.get('image_confidence'), self.input_tracker
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
            # 중지/오류로 중단되어 눌린 채 남은 키·마우스 버튼을 해제한다.
            self.input_tracker.release_all(self.c['log'])

            self.is_playing = False
            self.is_paused = False
            self.stop_event.clear()
            # PAUSE 복원도 여기서 함께 이루어진다.
            self.c['update_ui'](playing=False, paused=False)
            self.c['log']("🛑 재생 종료")
            self.c['update_status']("준비")

    def test_run_single_item(self, settings):
        if self.is_playing:
            self.c['log']("⚠️ 이미 실행 중입니다.")
            return

        self._exec_token = EXECUTION_LOCK.acquire("체인 테스트")
        if self._exec_token is None:
            self.c['log'](f"⚠️ '{EXECUTION_LOCK.current_label()}'이(가) 실행 중입니다. 먼저 중지해주세요.")
            return

        self.is_playing = True
        self.stop_event.clear()
        self.pause_event.set()

        # 토큰 획득 이후의 시작 절차 전체(UI 갱신 포함)를 실패 정리로 감싼다.
        try:
            self.c['update_ui'](playing=True)
            threading.Thread(target=self._run_single, args=(settings,), daemon=True).start()
        except Exception as e:
            self._abort_start(f"🔥 테스트 시작 실패: {e}")
            return

    def _run_single(self, settings):
        """실행 권한 반납을 보장하는 래퍼.

        본문이 어느 지점에서 실패하더라도(초기화 중 예외 포함) 최외곽 finally에서
        토큰과 pyautogui.PAUSE를 반드시 복원한다. 그렇지 않으면 락이 잡힌 채 남아
        앱 전체에서 매크로를 다시 시작할 수 없게 된다.
        """
        token = self._exec_token
        try:
            self._run_single_body(settings)
        finally:
            try:
                self.is_playing = False
                self.is_paused = False
            finally:
                EXECUTION_LOCK.release(token)
                self._exec_token = None
                # 락 해제 이후 상태를 UI에 반영한다. (해제 전 갱신은 잠긴 상태로 남는다)
                try:
                    self.c['update_ui'](**self._FINAL_UI)
                except Exception:
                    pass

    def _run_single_body(self, settings):
        self.c['log'](f"🧪 테스트: '{settings['playlist'][0]['display_name']}'")

        refresh_screen_info()
        reset_image_search_errors()

        # PAUSE는 EXECUTION_LOCK이 관리한다.
        try:
            MacroExecutor.execute_macro_item(
                settings['playlist'][0], self.c, self.stop_event, self.pause_event,
                settings['playback_speed'], settings['image_timeout'],
                settings.get('app'), settings.get('tree'),
                settings.get('image_confidence'), self.input_tracker
            )
        except Exception as e:
            self.c['log'](f"🔥 테스트 오류: {e}")
        finally:
            self.input_tracker.release_all(self.c['log'])
            self.is_playing = False
            self.c['update_ui'](playing=False)
            self.c['log']("🧪 테스트 완료")
            self.c['update_status']("준비")


# --- 3. 매크로 그룹 로직 클래스 ---
class ChainGroupMacro:
    # 래퍼가 락 반납 후 보낼 최종 UI 상태
    _FINAL_UI = {'playing': False, 'paused': False}

    def __init__(self, callbacks):
        self.c = callbacks
        self.is_playing = False
        self.is_paused = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        # 이 매크로의 실행이 누른 입력만 추적한다. (다른 탭 실행과 섞이지 않도록)
        self.input_tracker = InputTracker()
        self._exec_token = None

    def start_playback(self, settings):
        if self.is_playing: return
        if not settings['chain_playlist']:
            self.c['log']("⚠️ 그룹 목록이 비어있습니다.")
            return

        self._exec_token = EXECUTION_LOCK.acquire("그룹 재생")
        if self._exec_token is None:
            self.c['log'](f"⚠️ '{EXECUTION_LOCK.current_label()}'이(가) 실행 중입니다. 먼저 중지해주세요.")
            return

        self.is_playing = True
        self.is_paused = False
        self.stop_event.clear()
        self.pause_event.set()

        # 토큰 획득 이후의 시작 절차 전체(UI 갱신 포함)를 실패 정리로 감싼다.
        try:
            self.c['update_ui'](playing=True)
            threading.Thread(target=self.run_playback, args=(settings,), daemon=True).start()
        except Exception as e:
            self._abort_start(f"🔥 그룹 재생 시작 실패: {e}")
            return

    def _abort_start(self, message):
        """시작 도중 실패했을 때 상태·실행 권한·화면을 모두 되돌립니다.

        UI 갱신이나 스레드 시작 어느 쪽이 실패해도 작업 스레드의 최외곽 finally가
        돌지 않으므로, 여기서 토큰과 PAUSE(락이 함께 복원)를 직접 반납해야 한다.
        """
        self.is_playing = False
        self.is_paused = False
        EXECUTION_LOCK.release(self._exec_token)
        self._exec_token = None
        for call in (lambda: self.c['log'](message),
                     lambda: self.c['update_ui'](**self._FINAL_UI)):
            try:
                call()
            except Exception:
                pass

    def stop_playback(self):
        if not self.is_playing: return
        self.stop_event.set()
        self.pause_event.set()
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
        """실행 권한 반납을 보장하는 래퍼.

        본문이 어느 지점에서 실패하더라도(초기화 중 예외 포함) 최외곽 finally에서
        토큰과 pyautogui.PAUSE를 반드시 복원한다. 그렇지 않으면 락이 잡힌 채 남아
        앱 전체에서 매크로를 다시 시작할 수 없게 된다.
        """
        token = self._exec_token
        try:
            self._run_playback_body(settings)
        finally:
            try:
                self.is_playing = False
                self.is_paused = False
            finally:
                EXECUTION_LOCK.release(token)
                self._exec_token = None
                # 락 해제 이후 상태를 UI에 반영한다. (해제 전 갱신은 잠긴 상태로 남는다)
                try:
                    self.c['update_ui'](**self._FINAL_UI)
                except Exception:
                    pass

    def _run_playback_body(self, settings):
        self.c['log']("🚀 매크로 그룹 재생 시작")
        self.c['update_status']("그룹 실행 중")

        refresh_screen_info()
        reset_image_search_errors()

        # PAUSE는 EXECUTION_LOCK이 저장·복원한다.
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
                    if self.stop_event.is_set(): break

                    chain_path = chain_info['path']
                    chain_repeats = int(chain_info['repeats'])
                    chain_delay = float(chain_info['delay_after'])

                    self.c['log'](f"📂 그룹 ({chain_index+1}/{len(settings['chain_playlist'])}) '{os.path.basename(chain_path)}' 시작 (x{chain_repeats})")

                    # 체인 파일 로드
                    macro_playlist = self.c['load_macros_from_chain'](chain_path)
                    if macro_playlist is None:
                        self.c['log'](f"⚠️ 체인 로드 실패: {os.path.basename(chain_path)}")
                        self.stop_event.set()
                        break
                    if not macro_playlist:
                        self.c['log'](f"⚠️ 체인 내용 없음: {os.path.basename(chain_path)} (건너뜀)")
                        continue

                    # 해당 체인 반복
                    for i in range(chain_repeats):
                        if self.stop_event.is_set(): break
                        self.pause_event.wait()
                        if self.stop_event.is_set(): break

                        # 체인 내 아이템 실행
                        for macro_item in macro_playlist:
                            if self.stop_event.is_set(): break
                            success = MacroExecutor.execute_macro_item(
                                macro_item, self.c, self.stop_event, self.pause_event,
                                settings['playback_speed'], settings['image_timeout'],
                                settings.get('app'), settings.get('tree'),
                                settings.get('image_confidence'), self.input_tracker
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
            self.input_tracker.release_all(self.c['log'])

            self.is_playing = False
            self.is_paused = False
            self.stop_event.clear()
            # PAUSE 복원도 여기서 함께 이루어진다.
            self.c['update_ui'](playing=False, paused=False)
            self.c['log']("🛑 그룹 재생 종료")
            self.c['update_status']("준비")
