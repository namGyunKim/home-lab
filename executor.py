import time
import os
import pyautogui
from PIL import Image
from constants import ActionType, MacroType
# utils에서 캐시 함수 임포트 (성능 최적화)
from utils import get_cached_image

# 안전장치 활성화
pyautogui.FAILSAFE = True

# --- 매크로 실행 로직 ---

class MacroExecutor:
    @staticmethod
    def execute_macro_item(item_info, callbacks, stop_event, pause_event, speed, timeout, app=None, tree=None):
        """
        매크로 체인 목록의 단일 항목을 실행합니다.
        성공 또는 계속 진행 가능한 오류 시 True, 중지 또는 치명적 오류 시 False를 반환합니다.
        """
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
                callbacks['log'](f"⌛ '{os.path.basename(macro_data)}' 찾는 중 (최대 {timeout}초)...")
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
                        location = pyautogui.locateOnScreen(target_img, confidence=0.8, grayscale=True)
                        if location:
                            callbacks['log'](f"✅ '{os.path.basename(macro_data)}' 발견.")
                            found = True
                            break
                        time.sleep(0.2) # CPU 점유율 완화
                    except pyautogui.ImageNotFoundException:
                        # 최신 버전 pyautogui에서는 못 찾으면 예외 발생 가능
                        time.sleep(0.2)
                    except Exception as e:
                        # 기타 화면 인식 오류 무시하고 계속 시도
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
                    return False # 파일 로드 실패 시 중단
                if not actions:
                    callbacks['log'](f"⚠️ '{display_name}' 내용 없음.")
                    return True

                for action in actions:
                    # 일시정지 체크
                    while not pause_event.is_set():
                        if stop_event.is_set(): return False
                        time.sleep(0.1)

                    if stop_event.is_set(): return False

                    # 속도 적용 (0으로 나누기 방지)
                    safe_speed = max(0.1, speed)
                    delay = action.get('delay', 0) / safe_speed

                    # 딜레이 대기 (긴 딜레이 중 중지 가능하도록)
                    end_wait = time.time() + delay
                    while time.time() < end_wait:
                        if stop_event.is_set(): return False
                        time.sleep(min(0.05, end_wait - time.time())) # 0.1 -> 0.05 더 부드러운 중단

                    action_type = action['type']

                    # [수정] 좌표 유효성 검사 (화면 밖 클릭 방지)
                    pos = action.get('pos')
                    if pos:
                        x, y = pos
                        if not pyautogui.onScreen(x, y):
                            # 화면 밖이면 동작을 건너뛰거나 경고 (여기선 경고 후 진행 시도)
                            # callbacks['log'](f"⚠️ 좌표 벗어남 ({x}, {y}) - 무시함")
                            continue

                        try:
                            pyautogui.moveTo(x, y, duration=0)
                        except pyautogui.FailSafeException:
                            raise
                        except Exception:
                            pass # 좌표 오류 무시

                    # 동작 실행
                    if action_type == ActionType.MOUSE_DOWN.value:
                        pyautogui.mouseDown(button=action['button'])
                    elif action_type == ActionType.MOUSE_UP.value:
                        pyautogui.mouseUp(button=action['button'])
                    elif action_type == ActionType.KEY_DOWN.value:
                        pyautogui.keyDown(action['key'])
                    elif action_type == ActionType.KEY_UP.value:
                        pyautogui.keyUp(action['key'])

            # 실행 후 대기 시간 처리
            if stop_event.is_set(): return False

            item_delay = float(item_info.get('delay', 0))
            if item_delay > 0:
                end_wait = time.time() + item_delay
                while time.time() < end_wait:
                    if stop_event.is_set(): return False
                    time.sleep(min(0.1, end_wait - time.time()))

            return True

        except pyautogui.FailSafeException:
            callbacks['log']("🚨 페일세이프 발동! (마우스 모서리 감지 - 즉시 중단)")
            stop_event.set()
            return False
        except Exception as e:
            callbacks['log'](f"🔥 매크로 실행 중 오류: {e}")
            return False