import tkinter as tk
from tkinter import ttk, filedialog
import os
import json
from pynput import mouse, keyboard
from constants import RepeatMode
from macro_logic import AutoClickerMacro

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
        self.frenzy_mode_check = ttk.Checkbutton(settings_frame, text="활성화 (빠른 클릭)", variable=self.frenzy_mode_var)
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
        ttk.Radiobutton(repeat_mode_frame, text="횟수:", variable=self.repeat_mode_var, value=RepeatMode.COUNT.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
        self.repeat_count_entry = ttk.Entry(repeat_mode_frame, textvariable=self.repeat_value_var, width=8)
        self.repeat_count_entry.pack(side=tk.LEFT, padx=(2, 10))
        ttk.Radiobutton(repeat_mode_frame, text="시간(분):", variable=self.repeat_mode_var, value=RepeatMode.DURATION.name, command=self.toggle_repeat_entry).pack(side=tk.LEFT)
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
                    widget.config(state=state)

                if self.repeat_frame.winfo_exists():
                    for child in self.repeat_frame.winfo_children():
                        child.config(state=state)
                self.toggle_repeat_entry()

            if paused is not None:
                self.pause_button.config(text="재개 (F5)" if paused else "일시정지 (F5)")
        except tk.TclError: pass
