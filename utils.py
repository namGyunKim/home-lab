import os
import json
import glob
import re
import time
import pyautogui
from PIL import Image

# 안전장치 설정
pyautogui.FAILSAFE = True

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

    confidence = float(settings.get('confidence_level', 0.7))
    interval = float(settings.get('click_interval', 0.1))
    is_frenzy = settings.get('frenzy_mode', False)
    search_region = tuple(settings['search_area_coords']) if settings.get('use_search_area') and settings.get('search_area_coords') else None

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
            except Exception:
                location = None

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
                    time.sleep(min(0.05, end_time - time.time()))

        except pyautogui.FailSafeException:
            log_func("🚨 페일세이프 발동! (마우스 모서리 감지)")
            stop_event.set()
            return False
        except Exception as e:
            # log_func(f"오류 '{os.path.basename(image_path)}': {e}")
            pass

    return any_image_clicked