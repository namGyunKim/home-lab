import os
import sys
import json
import glob
import re
import time
import pyautogui
from PIL import Image

# 안전장치 설정
pyautogui.FAILSAFE = True

# --- 다중 모니터 좌표 판정 ---
# pyautogui.onScreen()은 주 모니터 영역만 유효 좌표로 판정하므로,
# 주 모니터 왼쪽/위쪽에 배치된 보조 모니터(음수 좌표)의 동작이 전부 무시된다.
# 그렇다고 가상 데스크톱의 경계 사각형만 검사하면, 크기가 다른 모니터를 나란히 둘 때
# 생기는 빈 영역(어느 모니터에도 속하지 않는 좌표)까지 통과시킨다.
# 따라서 각 모니터의 실제 영역 중 하나에 포함되는지로 판정한다.
_VIRTUAL_SCREEN_RECT = None
_MONITOR_RECTS = None

def refresh_screen_info():
    """모니터 구성 정보를 다시 계산합니다. (매크로 시작 시 호출)"""
    global _VIRTUAL_SCREEN_RECT, _MONITOR_RECTS
    _VIRTUAL_SCREEN_RECT = None
    _MONITOR_RECTS = None
    get_virtual_screen_rect()
    return get_monitor_rects()

# 예전 이름 호환
refresh_virtual_screen_rect = refresh_screen_info

def get_monitor_rects():
    """연결된 각 모니터의 영역 목록 [(left, top, right, bottom), ...]을 반환합니다."""
    global _MONITOR_RECTS
    if _MONITOR_RECTS is not None:
        return _MONITOR_RECTS

    rects = []
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.POINTER(wintypes.RECT), ctypes.c_ssize_t)

            def _collect(hmonitor, hdc, lprect, lparam):
                r = lprect.contents
                rects.append((r.left, r.top, r.right, r.bottom))
                return 1

            if not user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_collect), 0):
                rects = []
        except Exception:
            rects = []

    if not rects:
        # 모니터 목록을 얻지 못하면 가상 데스크톱 전체를 하나의 화면으로 취급한다.
        rect = get_virtual_screen_rect()
        if rect:
            left, top, width, height = rect
            rects = [(left, top, left + width, top + height)]

    _MONITOR_RECTS = rects
    return rects

def get_virtual_screen_rect():
    """모든 모니터를 포함하는 영역 (left, top, width, height)를 반환합니다."""
    global _VIRTUAL_SCREEN_RECT
    if _VIRTUAL_SCREEN_RECT is not None:
        return _VIRTUAL_SCREEN_RECT

    rect = None
    if sys.platform == "win32":
        try:
            from ctypes import windll
            user32 = windll.user32
            # SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77,
            # SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
            left = user32.GetSystemMetrics(76)
            top = user32.GetSystemMetrics(77)
            width = user32.GetSystemMetrics(78)
            height = user32.GetSystemMetrics(79)
            if width > 0 and height > 0:
                rect = (left, top, width, height)
        except Exception:
            rect = None

    if rect is None:
        try:
            size = pyautogui.size()
            rect = (0, 0, int(size[0]), int(size[1]))
        except Exception:
            rect = None

    _VIRTUAL_SCREEN_RECT = rect
    return rect

def is_on_screen(x, y):
    """좌표가 연결된 모니터 중 하나에 실제로 속하는지 판정합니다."""
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return False

    monitors = get_monitor_rects()
    if not monitors:
        # 화면 정보를 얻지 못하면 막지 않고 통과시킨다. (실패는 pyautogui가 처리)
        return True

    for left, top, right, bottom in monitors:
        if left <= x < right and top <= y < bottom:
            return True
    return False

# --- 이미지 캐싱 시스템 (성능 최적화) ---
# 구조: { 'file_path': {'mtime': timestamp, 'image': PIL.ImageObject} }
_IMAGE_CACHE = {}

def get_cached_image(image_path):
    """
    이미지를 메모리에 캐싱하여 디스크 I/O를 최소화합니다.
    파일이 수정된 경우에만 다시 로드합니다.
    """
    global _IMAGE_CACHE

    try:
        current_mtime = os.path.getmtime(image_path)

        # 캐시에 없거나, 파일이 수정되었다면 새로 로드
        if image_path not in _IMAGE_CACHE or _IMAGE_CACHE[image_path]['mtime'] != current_mtime:
            # 기존 이미지 닫기 (리소스 해제 시도)
            if image_path in _IMAGE_CACHE:
                try:
                    _IMAGE_CACHE[image_path]['image'].close()
                except: pass

            # 이미지 로드 (메모리에 유지)
            img = Image.open(image_path)
            # PIL 이미지를 강제로 로드하여 파일 핸들 의존성을 낮춤
            img.load()

            _IMAGE_CACHE[image_path] = {
                'mtime': current_mtime,
                'image': img
            }
            # print(f"[DEBUG] 이미지 캐시 로드/갱신: {os.path.basename(image_path)}") # 디버깅용

        return _IMAGE_CACHE[image_path]['image']

    except Exception as e:
        print(f"이미지 캐싱 오류 ({image_path}): {e}")
        return None

# --- 이미지 인식 오류 안내 ---
# 같은 오류가 매 프레임 반복되므로 종류별로 한 번씩만 로그를 남긴다.
_REPORTED_IMAGE_ERRORS = set()

def report_image_search_error(log_func, exc):
    """이미지 탐색 중 발생한 예외를 (종류별 1회) 사용자에게 알립니다."""
    key = type(exc).__name__
    if key in _REPORTED_IMAGE_ERRORS:
        return
    _REPORTED_IMAGE_ERRORS.add(key)

    message = str(exc)
    log_func(f"🔥 이미지 인식 실패: {key}: {message}")
    if isinstance(exc, TypeError) and 'confidence' in message:
        log_func("ℹ️ 정확도(confidence) 기능은 opencv-python이 필요합니다. "
                 "설치가 누락되면 이미지를 찾지 못합니다.")

def reset_image_search_errors():
    """매크로를 새로 시작할 때 오류 안내 기록을 초기화합니다."""
    _REPORTED_IMAGE_ERRORS.clear()

def clear_image_cache():
    """캐시된 모든 이미지를 해제합니다."""
    global _IMAGE_CACHE
    for data in _IMAGE_CACHE.values():
        try:
            data['image'].close()
        except: pass
    _IMAGE_CACHE.clear()
    print("이미지 캐시가 초기화되었습니다.")

# --- 이미지 처리 및 유틸리티 함수 ---

def execute_image_scan(log_func, image_folder_path, stop_event, pause_event):
    """
    지정된 폴더의 이미지를 한 번 스캔하여 클릭하는 함수.
    성공적으로 하나라도 클릭했는지 여부를 반환합니다.
    """
    config_path = os.path.join(image_folder_path, 'config.json')
    # 기본 설정값
    settings = {
        'confidence_level': 0.7,
        'click_interval': 0.1,
        'frenzy_mode': False,
        'use_search_area': False,
        'search_area_coords': None
    }

    # 설정 파일 로드
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_settings = json.load(f)
                settings.update(loaded_settings)
    except Exception as e:
        log_func(f"⚠️ config.json 로드 실패 (기본값 사용): {e}")

    def _safe_float(val, default):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    # 숫자 설정은 사용자가 직접 입력/수정할 수 있으므로 방어적으로 파싱
    confidence = _safe_float(settings.get('confidence_level', 0.7), 0.7)
    confidence = max(0.1, min(1.0, confidence))

    interval = _safe_float(settings.get('click_interval', 0.1), 0.1)
    interval = max(0.0, interval)

    is_frenzy = bool(settings.get('frenzy_mode', False))

    # 검색 영역(Region)도 형식/값 검증 후 사용
    search_region = None
    if bool(settings.get('use_search_area')) and settings.get('search_area_coords'):
        coords = settings.get('search_area_coords')
        if isinstance(coords, (list, tuple)) and len(coords) == 4:
            try:
                x, y, w, h = (int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3]))
                if w > 0 and h > 0:
                    search_region = (x, y, w, h)
            except Exception:
                search_region = None

    # 이미지 파일 검색
    search_pattern = os.path.join(image_folder_path, 'image*.png')
    all_files = glob.glob(search_pattern)

    # 파일명 자연 정렬
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', os.path.basename(s))]

    image_files = sorted(all_files, key=natural_sort_key)

    if not image_files:
        return False

    any_image_clicked = False

    for image_path in image_files:
        # 중지/일시정지 체크
        if stop_event.is_set():
            log_func("🛑 이미지 스캔 중지.")
            break

        while not pause_event.is_set():
            if stop_event.is_set(): break
            time.sleep(0.1)

        try:
            # [개선] 캐시된 이미지 사용
            img = get_cached_image(image_path)
            if img is None: continue

            # 이미지 매칭 시도
            try:
                location = pyautogui.locateCenterOnScreen(
                    img,
                    confidence=confidence,
                    grayscale=True,
                    region=search_region
                )
            except pyautogui.ImageNotFoundException:
                location = None
            except Exception as e:
                # [수정] 예외를 조용히 삼키면 "실행은 되는데 아무것도 안 하는" 상태가 된다.
                # opencv 누락(confidence 사용 불가), 화면 캡처 실패 등은 반드시 알린다.
                location = None
                report_image_search_error(log_func, e)

            if location:
                # 클릭 수행
                if is_frenzy:
                    pyautogui.click(location, clicks=3, interval=0.01)
                    log_func(f"✅ ⚡ 3회: '{os.path.basename(image_path)}'")
                else:
                    pyautogui.click(location)
                    log_func(f"✅ 클릭: '{os.path.basename(image_path)}'")

                any_image_clicked = True

                # 클릭 후 딜레이 (CPU 양보)
                end_time = time.time() + interval
                while time.time() < end_time:
                    if stop_event.is_set(): break
                    time.sleep(max(0.0, min(0.05, end_time - time.time())))

        except pyautogui.FailSafeException:
            log_func("🚨 페일세이프 발동! (마우스 모서리 감지)")
            stop_event.set()
            return False
        except Exception as e:
            # log_func(f"오류 '{os.path.basename(image_path)}': {e}")
            pass

    return any_image_clicked
