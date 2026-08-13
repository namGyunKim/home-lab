import time
import os
import threading
import pyautogui
from PIL import Image
from constants import ActionType, MacroType
# utils에서 캐시 함수 임포트 (성능 최적화)
from utils import get_cached_image, is_on_screen, report_image_search_error

# 안전장치 활성화
pyautogui.FAILSAFE = True


# --- 실행 상호 배제 ---
# 체인 재생 / 체인 테스트 / 그룹 재생 / 이미지 매크로 / 녹화는 모두
# 하나뿐인 마우스 포인터와 키보드, 그리고 전역 `pyautogui.PAUSE`를 공유한다.
# 둘 이상이 동시에 돌면 입력 순서가 섞이고, 같은 키를 양쪽이 누른 경우
# 한쪽의 종료 처리가 상대가 유지해야 할 키까지 떼어 버린다.
# 따라서 충돌하는 작업은 한 번에 하나만 실행되도록 중재한다.
class ExecutionLock:
    def __init__(self):
        self._lock = threading.Lock()
        self._token = None
        self._label = None
        self._saved_pause = None

    def acquire(self, label, adjust_pause=True):
        """실행 권한을 얻으면 토큰을, 이미 다른 작업이 실행 중이면 None을 반환합니다."""
        with self._lock:
            if self._token is not None:
                return None
            self._token = object()
            self._label = label
            if adjust_pause:
                # PAUSE 저장/복원을 한곳에서 관리해 중첩으로 값이 어긋나는 것을 막는다.
                self._saved_pause = pyautogui.PAUSE
                pyautogui.PAUSE = 0.01
            return self._token

    def release(self, token):
        """자신이 얻은 토큰일 때만 실행 권한을 반납합니다."""
        with self._lock:
            if token is None or token is not self._token:
                return False
            if self._saved_pause is not None:
                pyautogui.PAUSE = self._saved_pause
                self._saved_pause = None
            self._token = None
            self._label = None
            return True

    def current_label(self):
        with self._lock:
            return self._label

    def is_busy(self):
        with self._lock:
            return self._token is not None


EXECUTION_LOCK = ExecutionLock()

# 이미지 대기 기본 정확도 (재생 설정에서 변경 가능)
DEFAULT_IMAGE_CONFIDENCE = 0.8

# --- 눌린 입력 추적 ---
# key_down / mouse_down 만 실행된 상태에서 중지·오류로 빠져나가면
# 키나 버튼이 눌린 채로 남아 시스템 전체가 오작동한다. 종료 시 반드시 해제한다.
#
# 추적 상태는 모듈 전역이 아니라 **실행 단위**로 관리한다.
# 전역으로 두면 체인 재생과 그룹 재생이 동시에 돌 때 한쪽의 종료 처리가
# 다른 쪽이 누르고 있는 키까지 해제해 버린다.
class InputTracker:
    """한 번의 매크로 실행이 누른 키/마우스 버튼을 추적합니다."""

    def __init__(self):
        self._keys = set()
        self._buttons = set()

    def key_down(self, key_name):
        pyautogui.keyDown(key_name)
        self._keys.add(key_name)

    def key_up(self, key_name):
        pyautogui.keyUp(key_name)
        self._keys.discard(key_name)

    def mouse_down(self, button):
        pyautogui.mouseDown(button=button)
        self._buttons.add(button)

    def mouse_up(self, button):
        pyautogui.mouseUp(button=button)
        self._buttons.discard(button)

    def release_all(self, log_func=None):
        """이 실행이 누른 채 남긴 키와 마우스 버튼만 해제합니다."""
        released = []

        for button in list(self._buttons):
            try:
                pyautogui.mouseUp(button=button)
                released.append(f"마우스 {button}")
            except Exception:
                pass
            self._buttons.discard(button)

        for key_name in list(self._keys):
            try:
                pyautogui.keyUp(key_name)
                released.append(str(key_name))
            except Exception:
                pass
            self._keys.discard(key_name)

        if released and log_func:
            log_func(f"🔓 눌린 채 남은 입력을 해제했습니다: {', '.join(released)}")
        return released

# --- 키 이름 정규화 (pynput -> pyautogui) ---
# pynput에서 저장되는 키 이름과 pyautogui에서 기대하는 키 이름이 일부 다릅니다.
# (예: ctrl_l -> ctrlleft)
_KEY_NAME_MAP = {
    'ctrl_l': 'ctrlleft',
    'ctrl_r': 'ctrlright',
    'alt_l': 'altleft',
    'alt_r': 'altright',
    'shift_l': 'shiftleft',
    'shift_r': 'shiftright',
    'cmd_l': 'winleft',
    'cmd_r': 'winright',
    'caps_lock': 'capslock',
    'page_up': 'pageup',
    'page_down': 'pagedown',
    'print_screen': 'printscreen',
    'scroll_lock': 'scrolllock',
    'num_lock': 'numlock',
}


def _normalize_key_name(key_name):
    if not isinstance(key_name, str):
        return key_name
    key_lower = key_name.lower()
    return _KEY_NAME_MAP.get(key_lower, key_lower)


# --- 매크로 실행 로직 ---

class MacroExecutor:
    @staticmethod
    def execute_macro_item(item_info, callbacks, stop_event, pause_event, speed, timeout,
                           app=None, tree=None, image_confidence=None, tracker=None):
        """
        매크로 체인 목록의 단일 항목을 실행합니다.
        성공 또는 계속 진행 가능한 오류 시 True, 중지 또는 치명적 오류 시 False를 반환합니다.

        tracker: 이 실행이 누른 입력을 추적할 InputTracker.
                 넘기지 않으면 항목 단위로 만들고 항목이 끝날 때 해제한다.
        """
        owns_tracker = tracker is None
        if owns_tracker:
            tracker = InputTracker()
        # UI 선택 업데이트 (메인 스레드 요청)
        if app and tree and item_info.get('item_id'):
            try:
                app.root.after(0, app.update_tree_selection, tree, item_info['item_id'])
            except Exception: pass

        # 일시정지 대기
        while not pause_event.is_set():
            if stop_event.is_set(): return False
            time.sleep(0.1)

        if stop_event.is_set(): return False

        macro_type = item_info['type']
        macro_data = item_info['data']
        display_name = item_info['display_name']

        callbacks['log'](f"▶️ '{display_name}' 실행 시작...")

        try:
            # 1. 이미지 대기 매크로
            if macro_type == MacroType.IMAGE_WAIT.value:
                # [수정] 정확도를 재생 설정에서 받아 사용 (해상도가 다른 PC 대응)
                try:
                    confidence = float(image_confidence) if image_confidence is not None else DEFAULT_IMAGE_CONFIDENCE
                except (TypeError, ValueError):
                    confidence = DEFAULT_IMAGE_CONFIDENCE
                confidence = max(0.1, min(1.0, confidence))

                callbacks['log'](f"⌛ '{os.path.basename(macro_data)}' 찾는 중 "
                                 f"(최대 {timeout}초, 정확도 {confidence})...")
                wait_start = time.time()
                found = False

                # [수정] 직접 Image.open 하지 않고 utils의 캐시된 이미지 사용 (성능 향상)
                target_img = get_cached_image(macro_data)
                if target_img is None:
                    callbacks['log'](f"⚠️ 이미지 파일 로드 실패: {os.path.basename(macro_data)}")
                    return True # 파일 문제면 건너뜀

                while not stop_event.is_set():
                    # 타임아웃 체크
                    if (time.time() - wait_start) >= timeout:
                        break

                    # 일시정지 체크
                    while not pause_event.is_set():
                        if stop_event.is_set(): break
                        time.sleep(0.1)

                    try:
                        # locateOnScreen 개선: 예외 처리 강화
                        location = pyautogui.locateOnScreen(target_img, confidence=confidence, grayscale=True)
                        if location:
                            callbacks['log'](f"✅ '{os.path.basename(macro_data)}' 발견.")
                            found = True
                            break
                        time.sleep(0.2) # CPU 점유율 완화
                    except pyautogui.ImageNotFoundException:
                        # 최신 버전 pyautogui에서는 못 찾으면 예외 발생 가능
                        time.sleep(0.2)
                    except Exception as e:
                        # [수정] 조용히 넘기면 원인을 알 수 없으므로 종류별 1회 알림
                        report_image_search_error(callbacks['log'], e)
                        time.sleep(0.5)

                # 리소스 해제는 utils의 캐시 시스템이 관리하므로 여기서 close() 하지 않음

                if not found:
                    if not stop_event.is_set():
                        callbacks['log'](f"⚠️ 시간 초과: '{os.path.basename(macro_data)}' 미발견 (넘어감)")
                    return True

            # 2. 파일/메모리(녹화) 매크로
            else:
                actions = macro_data if macro_type == MacroType.MEMORY.value else callbacks['load_actions_from_file'](macro_data)
                if actions is None:
                    callbacks['log'](f"⚠️ '{display_name}' 로드 실패로 이 항목을 건너뜁니다.")
                    return True
                if not actions:
                    callbacks['log'](f"⚠️ '{display_name}' 내용 없음.")
                    return True

                skipped_positions = []
                for action in actions:
                    # 일시정지 체크
                    while not pause_event.is_set():
                        if stop_event.is_set(): return False
                        time.sleep(0.1)

                    if stop_event.is_set(): return False

                    # 속도 적용 (0으로 나누기 방지)
                    safe_speed = max(0.1, speed)

                    # 딜레이 값 방어적 파싱
                    try:
                        action_delay = float(action.get('delay', 0) or 0)
                    except (TypeError, ValueError):
                        action_delay = 0

                    delay = action_delay / safe_speed

                    # 딜레이 대기 (긴 딜레이 중 중지 가능하도록)
                    end_wait = time.time() + delay
                    while time.time() < end_wait:
                        if stop_event.is_set(): return False
                        time.sleep(max(0.0, min(0.05, end_wait - time.time()))) # 0.1 -> 0.05 더 부드러운 중단

                    action_type = action['type']

                    # [수정] 좌표 유효성 검사
                    # 판정 기준을 주 모니터가 아닌 가상 데스크톱(모든 모니터)으로 변경.
                    # 기존에는 주 모니터 왼쪽/위에 있는 보조 모니터 좌표가 전부 '화면 밖'으로
                    # 판정되어 해당 동작이 통째로 무시되었다.
                    pos = action.get('pos')
                    if pos and isinstance(pos, (list, tuple)) and len(pos) == 2:
                        x, y = pos
                        if is_on_screen(x, y):
                            try:
                                pyautogui.moveTo(x, y, duration=0)
                            except pyautogui.FailSafeException:
                                raise
                            except Exception:
                                pass # 좌표 오류 무시
                        else:
                            skipped_positions.append((x, y))
                            # 버튼을 떼는 동작까지 건너뛰면 마우스가 눌린 채로 남으므로
                            # MOUSE_UP은 좌표와 무관하게 반드시 실행한다.
                            if action_type != ActionType.MOUSE_UP.value:
                                continue

                    # 동작 실행
                    if action_type == ActionType.MOUSE_DOWN.value:
                        tracker.mouse_down(action['button'])
                    elif action_type == ActionType.MOUSE_UP.value:
                        tracker.mouse_up(action['button'])
                    elif action_type == ActionType.KEY_DOWN.value:
                        tracker.key_down(_normalize_key_name(action['key']))
                    elif action_type == ActionType.KEY_UP.value:
                        tracker.key_up(_normalize_key_name(action['key']))

                if skipped_positions:
                    first = skipped_positions[0]
                    callbacks['log'](
                        f"⚠️ '{display_name}': 화면 밖 좌표 {len(skipped_positions)}개를 건너뛰었습니다. "
                        f"(예: {first[0]}, {first[1]}) 녹화 당시와 모니터 구성/해상도가 다른지 확인하세요."
                    )

            # 실행 후 대기 시간 처리
            if stop_event.is_set(): return False

            try:
                item_delay = float(item_info.get('delay', 0) or 0)
            except (TypeError, ValueError):
                callbacks['log'](f"⚠️ '{display_name}' 실행 후 대기값이 숫자가 아니어서 0초로 처리합니다: {item_info.get('delay')}")
                item_delay = 0
            if item_delay > 0:
                end_wait = time.time() + item_delay
                while time.time() < end_wait:
                    if stop_event.is_set(): return False
                    time.sleep(max(0.0, min(0.1, end_wait - time.time())))

            return True

        except pyautogui.FailSafeException:
            callbacks['log']("🚨 페일세이프 발동! (마우스 모서리 감지 - 즉시 중단)")
            stop_event.set()
            return False
        except Exception as e:
            callbacks['log'](f"🔥 매크로 실행 중 오류: {e}")
            return False
        finally:
            # 호출자가 tracker를 관리하면 재생 종료 시점에 해제하므로 여기서 건드리지 않는다.
            if owns_tracker:
                tracker.release_all(callbacks.get('log'))
