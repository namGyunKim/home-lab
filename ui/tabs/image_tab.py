import tkinter as tk
from tkinter import ttk, filedialog
import os
import json
import threading
from pynput import mouse, keyboard
from constants import RepeatMode
from macro_logic import AutoClickerMacro
from executor import EXECUTION_LOCK
from ui.metrics import set_widget_state_recursive

class GlobalAreaSelector:
    def __init__(self, tab, exec_token=None):
        self.tab = tab
        # 영역 선택도 전역 마우스/키보드 리스너로 다음 클릭을 가로채므로
        # 매크로 실행과 겹치면 엉뚱한 좌표가 영역으로 잡힌다. 실행 권한을 함께 점유한다.
        self.exec_token = exec_token
        self._token_released = False
        # 콜백 활성 여부. 정리에 실패해 리스너가 살아남더라도 이 플래그로 즉시 무력화한다.
        self._active = True
        # 클릭 처리와 ESC 취소가 겹치지 않도록 직렬화한다.
        self._lock = threading.RLock()
        self.start_pos = None
        self.mouse_listener = None
        self.keyboard_listener = None
        try:
            self.mouse_listener = mouse.Listener(on_click=self.on_click)
            self.keyboard_listener = keyboard.Listener(on_press=self.on_press)
            self.mouse_listener.start()
            self.keyboard_listener.start()
        except Exception:
            # 한쪽만 시작된 채 남으면 이후 클릭을 계속 가로챈다.
            # 정상 종료와 **같은 정리 경로**를 타야 콜백 무력화(_active=False)와
            # 잔존 리스너 추적·경고까지 함께 이루어진다.
            # (여기서 _stop_listeners()만 부르면 생성에 실패한 객체의 콜백이 살아남는다)
            try:
                self.cleanup()
            except Exception:
                pass
            raise

    def is_alive(self):
        if not self._active:
            return False
        listener = self.mouse_listener
        try:
            return bool(listener and listener.is_alive())
        except Exception:
            return False

    def has_surviving_listeners(self):
        """중지에 실패해 아직 살아 있는 리스너가 있는지 확인합니다."""
        for attr in ('mouse_listener', 'keyboard_listener'):
            listener = getattr(self, attr, None)
            if listener is None:
                continue
            try:
                if listener.is_alive():
                    return True
            except Exception:
                return True
        return False

    def _dispatch(self, func, *args):
        """리스너 콜백 스레드에서 Tk 작업을 메인 스레드로 넘깁니다."""
        try:
            self.tab.after(0, lambda: func(*args))
        except Exception:
            pass

    def _dispatch_if_active(self, func, *args):
        """선택이 아직 진행 중일 때만 수행하는 Tk 작업을 넘깁니다.

        예약과 실행 사이에 ESC 취소가 끼어들 수 있으므로, 실행 시점에 다시 확인한다.
        (그렇지 않으면 취소가 끝난 뒤 "시작점 설정" 안내가 뒤늦게 표시된다)
        """
        def run_if_active():
            with self._lock:
                if not self._active:
                    return
            func(*args)
        try:
            self.tab.after(0, run_if_active)
        except Exception:
            pass

    def _claim(self):
        """이 콜백이 선택을 종료시킬 권리를 얻습니다.

        클릭 처리와 ESC 취소가 겹칠 때 **먼저 도착한 쪽만** 통과시킨다.
        (진입 시 한 번만 검사하면, 검사를 통과한 클릭이 ESC 정리 이후에
         영역을 설정해 버리는 경쟁이 생긴다)
        """
        with self._lock:
            if not self._active:
                return False
            self._active = False
            return True

    def on_press(self, key):
        if key != keyboard.Key.esc:
            return
        if not self._claim():
            return   # 이미 다른 콜백이 종료를 확정했거나 정리된 선택기
        # 로그/상태 갱신이 실패하더라도 리스너와 실행 권한은 반드시 정리한다.
        try:
            self._dispatch(self.tab.log, "영역 설정을 취소했습니다.")
            self._dispatch(self.tab.app.update_status, "준비")
        finally:
            self.cleanup()

    def on_click(self, x, y, button, pressed):
        if button != mouse.Button.left or not pressed: return

        # 첫 클릭(시작점)과 두 번째 클릭(확정) 판정을 한 경계 안에서 처리한다.
        with self._lock:
            if not self._active:
                return   # 이미 정리된 선택기 — 살아남은 리스너의 입력은 무시한다
            if self.start_pos is None:
                self.start_pos = (x, y)
                start_only = True
            else:
                start_only = False
                end_pos = (x, y)
                left = min(self.start_pos[0], end_pos[0])
                top = min(self.start_pos[1], end_pos[1])
                width = abs(self.start_pos[0] - end_pos[0])
                height = abs(self.start_pos[1] - end_pos[1])
                self._active = False   # 여기서 종료를 확정 — 이후 ESC는 통과하지 못한다

        if start_only:
            # 취소가 먼저 처리됐다면 이 안내는 버린다.
            self._dispatch_if_active(self.tab.log, f"시작점 설정: {self.start_pos}")
            return

        # 영역이 확정됐으므로, 이후 처리 성공 여부와 무관하게 정리한다.
        try:
            if width > 0 and height > 0:
                self._dispatch(self.tab.set_area, left, top, width, height)
            else:
                self._dispatch(self.tab.log, "⚠️ 영역이 유효하지 않습니다. 다시 시도해주세요.")
        finally:
            self.cleanup()

    def _stop_listeners(self):
        """두 리스너를 서로 독립적으로 중지합니다.

        한쪽 정리가 실패해도 다른 쪽은 반드시 중지되어야 한다.
        중지에 실패해 살아남은 리스너는 참조를 **비우지 않고 유지**해 추적 가능하게 둔다.
        (참조를 지워 버리면 살아 있는 리스너가 이후 클릭을 계속 가로채는데도 알 수 없다.)
        살아남은 리스너의 목록을 반환한다.
        """
        surviving = []
        for attr in ('mouse_listener', 'keyboard_listener'):
            listener = getattr(self, attr, None)
            if listener is None:
                continue

            stopped = False
            for _ in range(2):   # 일시적 실패를 감안해 한 번 더 시도
                try:
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

    def cleanup(self):
        # 먼저 콜백을 비활성화한다. 리스너가 살아남더라도 입력이 처리되지 않게 하기 위함.
        with self._lock:
            self._active = False
        surviving = []
        try:
            surviving = self._stop_listeners()
        finally:
            if surviving:
                self._dispatch(
                    self.tab.log,
                    f"⚠️ 영역 설정 리스너({', '.join(surviving)})를 중지하지 못했습니다. "
                    "입력은 무시되지만 문제가 계속되면 프로그램을 다시 시작해주세요."
                )
            # 리스너 정리가 실패해도 실행 권한은 반드시 반납한다.
            self._release_token()
        return surviving

    def _release_token(self):
        if self._token_released:
            return
        self._token_released = True
        EXECUTION_LOCK.release(self.exec_token)
        self.exec_token = None
        # 리스너 콜백 스레드에서 호출되므로 UI 갱신은 메인 스레드로 넘긴다.
        self._dispatch(self.tab.app.refresh_execution_state)

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
            # [수정] 상대 경로로 저장된 경우 절대 경로로 변환
            if last_folder and not os.path.isabs(last_folder):
                # 설정은 app.base_dir 기준 상대 경로로 저장되므로, 복원도 동일 기준을 사용
                last_folder = os.path.normpath(os.path.join(self.app.base_dir, last_folder))

            if last_folder and os.path.isdir(last_folder):
                self.image_folder_path.set(last_folder)
                self.load_settings()

    def log(self, message):
        self.app.log(f"[이미지] {message}")

    def _create_widgets(self):
        settings_frame = ttk.LabelFrame(self, text="이미지 매크로 설정", style="Card.TLabelframe")
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
        self.folder_button = ttk.Button(settings_frame, text="폴더 선택", style="Ghost.TButton", command=self.select_folder)
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
        self.frenzy_mode_check = ttk.Checkbutton(settings_frame, text="활성화 (빠른 클릭)", variable=self.frenzy_mode_var)
        self.frenzy_mode_check.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        r += 1
        ttk.Label(settings_frame, text="검색 영역:").grid(row=r, column=0, sticky=tk.W, padx=5, pady=2)
        self.use_search_area_check = ttk.Checkbutton(settings_frame, text="활성화", variable=self.use_search_area_var)
        self.use_search_area_check.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        self.set_area_button = ttk.Button(settings_frame, text="영역 설정 (F9)", style="Ghost.TButton", command=self.start_defining_area)
        self.set_area_button.grid(row=r, column=2, padx=5, pady=2)
        r += 1
        self.search_area_label = ttk.Label(settings_frame, textvariable=self.search_area_display_var, style="InfoAccent.TLabel")
        self.search_area_label.grid(row=r, column=1, columnspan=2, sticky=tk.W, padx=5, pady=2)
        settings_frame.columnconfigure(1, weight=1)
        self.repeat_frame = ttk.LabelFrame(self, text="반복 설정", style="Card.TLabelframe")
        self.repeat_frame.pack(fill=tk.X, padx=10, pady=5)
        self.repeat_mode_var = tk.StringVar(value=RepeatMode.INFINITE.name)
        # [수정] 횟수와 시간(분)이 같은 변수를 공유해 모드를 바꾸면 값이 섞였다. 분리한다.
        self.repeat_count_var = tk.StringVar(value="10")
        self.repeat_duration_var = tk.StringVar(value="10")
        self.repeat_delay_var = tk.StringVar(value="1.0")
        repeat_mode_frame = ttk.Frame(self.repeat_frame)
        repeat_mode_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        ttk.Radiobutton(repeat_mode_frame, text="무한 반복", variable=self.repeat_mode_var, value=RepeatMode.INFINITE.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(repeat_mode_frame, text="횟수:", variable=self.repeat_mode_var, value=RepeatMode.COUNT.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_count_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_count_var, width=8)
        self.repeat_count_entry.pack(side=tk.LEFT, padx=(2, 10))
        ttk.Radiobutton(repeat_mode_frame, text="시간(분):", variable=self.repeat_mode_var, value=RepeatMode.DURATION.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_duration_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_duration_var, width=8)
        self.repeat_duration_entry.pack(side=tk.LEFT, padx=2)
        repeat_delay_frame = ttk.Frame(self.repeat_frame)
        repeat_delay_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        ttk.Label(repeat_delay_frame, text="각 순회 후 대기(초):").pack(side=tk.LEFT)
        ttk.Entry(repeat_delay_frame, textvariable=self.repeat_delay_var, width=8).pack(side=tk.LEFT, padx=2)
        self.toggle_repeat_entry()
        control_frame = ttk.LabelFrame(self, text="제어", style="Card.TLabelframe")
        control_frame.pack(fill=tk.BOTH, padx=10, pady=5, expand=True)
        control_frame.columnconfigure((0,1,2), weight=1)
        self.start_button = ttk.Button(control_frame, text="시작 (F3)", style="Accent.TButton", command=self.start_macro)
        self.start_button.grid(row=0, column=0, sticky=tk.EW, padx=5, pady=5)
        self.pause_button = ttk.Button(control_frame, text="일시정지 (F5)", style="Neutral.TButton", command=self.macro.pause_or_resume, state=tk.DISABLED)
        self.pause_button.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.stop_button = ttk.Button(control_frame, text="중지 (F4)", style="Danger.TButton", command=self.macro.stop, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=2, sticky=tk.EW, padx=5, pady=5)

    def toggle_repeat_entry(self):
        try:
            if not self.repeat_frame.winfo_exists(): return
            # [수정] 실행 중에는 선택된 모드의 입력칸도 잠근 상태를 유지한다.
            busy = self.macro.is_running
            mode = self.repeat_mode_var.get()
            count_on = (not busy) and mode == RepeatMode.COUNT.name
            duration_on = (not busy) and mode == RepeatMode.DURATION.name
            self.repeat_count_entry.config(state=tk.NORMAL if count_on else tk.DISABLED)
            self.repeat_duration_entry.config(state=tk.NORMAL if duration_on else tk.DISABLED)
        except tk.TclError: pass

    def start_macro(self):
        self.save_settings()
        try:
            repeat_mode = RepeatMode[self.repeat_mode_var.get()]
            if repeat_mode == RepeatMode.COUNT:
                repeat_value = int(self.repeat_count_var.get())
            elif repeat_mode == RepeatMode.DURATION:
                repeat_value = float(self.repeat_duration_var.get())
            else:
                repeat_value = 0  # 무한 반복은 값을 쓰지 않는다.

            settings = {
                'image_folder': self.image_folder_path.get(),
                'repeat_mode': repeat_mode,
                'repeat_value': repeat_value,
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

        # 매크로 실행 중에는 클릭이 섞이므로 영역 설정을 시작하지 않는다.
        token = EXECUTION_LOCK.acquire("영역 설정", adjust_pause=False)
        if token is None:
            self.log(f"⚠️ '{EXECUTION_LOCK.current_label()}'이(가) 실행 중입니다. 먼저 중지해주세요.")
            return

        # 토큰을 얻은 뒤의 준비 과정 전체를 감싼다.
        # 안내 로그나 상태 갱신이 실패해도 실행 권한이 잠긴 채 남으면 안 된다.
        try:
            self.log("영역의 시작점을 클릭하고, 끝점을 다시 클릭하세요. (ESC: 취소)")
            self.app.update_status("화면 영역 설정 중...")
            self.area_selector = GlobalAreaSelector(self, token)
        except Exception as e:
            EXECUTION_LOCK.release(token)
            self.area_selector = None
            try:
                self.log(f"🔥 영역 설정 시작 실패: {e}")
                self.app.update_status("준비")
            except Exception:
                pass
            return
        self.app.refresh_execution_state()

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

    # --- [중요] 안정성 개선: UI 업데이트 스레드 안전성 확보 ---
    def update_ui_state(self, running=None, paused=None):
        """백그라운드 스레드에서 호출되더라도 안전하게 메인 스레드에서 실행합니다."""
        self.after(0, lambda: self._update_ui_state_safe(running, paused))

    def _update_ui_state_safe(self, running, paused):
        try:
            if running is not None:
                is_running = running
                state = tk.DISABLED if is_running else tk.NORMAL
                self.start_button.config(state=state)
                self.stop_button.config(state=tk.NORMAL if is_running else tk.DISABLED)
                self.pause_button.config(state=tk.NORMAL if is_running else tk.DISABLED)

                # 설정 위젯들 비활성화/활성화
                widgets_to_toggle = [
                    self.folder_button, self.confidence_entry, self.frenzy_mode_check,
                    self.use_search_area_check, self.set_area_button, self.interval_entry
                ]
                for widget in widgets_to_toggle:
                    try:
                        widget.config(state=state)
                    except tk.TclError:
                        pass

                if self.repeat_frame.winfo_exists():
                    # [수정] Frame 안의 반복 모드 라디오버튼까지 재귀적으로 상태를 적용한다.
                    set_widget_state_recursive(self.repeat_frame, state)
                self.toggle_repeat_entry()

            if paused is not None:
                self.pause_button.config(text="재개 (F5)" if paused else "일시정지 (F5)")
            # 실행 상태가 바뀌었으므로 다른 탭의 시작 버튼도 갱신한다.
            if hasattr(self.app, 'refresh_execution_state'):
                self.app.refresh_execution_state()
        except tk.TclError: pass

    def refresh_busy_state(self):
        """어떤 작업이든 실행 중이면 이 탭의 시작 계열 버튼을 잠급니다."""
        try:
            state = tk.DISABLED if EXECUTION_LOCK.is_busy() else tk.NORMAL
            self.start_button.config(state=state)
            # 영역 설정도 전역 입력을 가로채므로 함께 잠근다.
            self.set_area_button.config(state=state)
        except tk.TclError:
            pass
