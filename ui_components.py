import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import tkinter.font as tkFont
import os
import json
import threading
import webbrowser
from pynput import mouse, keyboard
from constants import RepeatMode, MacroType
from macro_logic import AutoClickerMacro, RecordingMacro, ChainGroupMacro

# --- GUI 탭 클래스 정의 ---

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
            # [수정] 상대 경로로 저장된 경우 절대 경로로 변환
            if last_chain and not os.path.isabs(last_chain):
                # 설정은 app.base_dir 기준 상대 경로로 저장되므로, 복원도 동일 기준을 사용
                last_chain = os.path.normpath(os.path.join(self.app.base_dir, last_chain))

            if last_chain and os.path.isfile(last_chain):
                self.load_chain(path=last_chain)

    def _set_dirty(self, dirty=True):
        if self.is_dirty == dirty: return
        self.is_dirty = dirty
        if hasattr(self.app, 'refresh_title'):
            self.app.refresh_title()
        else:
            title = getattr(self.app, 'title_base', '푸크로')
            if dirty: title += '*'
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
            # [상대 경로 처리] 체인 파일이 있는 폴더 기준으로 상대 경로 저장
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
                # [상대 경로 처리] 파일 로드 시 절대 경로로 복원
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
            if threading.current_thread() is not threading.main_thread():
                self.log("⚠️ 재생 중에는 파일 선택 창을 열 수 없어 해당 항목을 건너뜁니다. 재생을 멈춘 뒤 경로를 수정해주세요.")
                return None
            new_path = filedialog.askopenfilename(title=f"'{os.path.basename(file_path)}' 찾기", filetypes=[("JSON files", "*.json")])
            if new_path:
                updated_count = 0
                for item_id, item_info in self.playlist_data.items():
                    if item_info.get('data') == file_path:
                        item_info['data'] = new_path
                        self.macro_tree.set(item_id, "#1", os.path.basename(new_path))
                        updated_count += 1
                if updated_count > 0:
                    self._set_dirty()
                return self.load_actions_from_file(new_path)
            return None
        except Exception as e:
            self.log(f"🔥 '{os.path.basename(file_path)}' 파일 로드 실패: {e}")
            return None

    # --- [중요] 안정성 개선: UI 업데이트 스레드 안전성 확보 ---
    def update_ui_state(self, recording=None, playing=None, paused=None):
        """백그라운드 스레드에서 호출되더라도 안전하게 메인 스레드에서 실행합니다."""
        self.after(0, lambda: self._update_ui_state_safe(recording, playing, paused))

    def _update_ui_state_safe(self, recording, playing, paused):
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

                widgets_to_toggle = [
                    self.add_file_button, self.add_wait_image_button, self.remove_button,
                    self.up_button, self.down_button, self.clear_button, self.save_chain_button,
                    self.load_chain_button, self.save_as_chain_button, self.test_run_button
                ]
                for btn in widgets_to_toggle:
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
        if len(selected_items) == 1:
            self.test_run_button.config(state=tk.NORMAL)
            item_id = selected_items[0]
            item_data = self.playlist_data.get(item_id)
            if item_data and item_data['type'] == MacroType.MEMORY.value:
                self.save_button.config(state=tk.NORMAL)
            else:
                self.save_button.config(state=tk.DISABLED)
        else:
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
            # [수정] 상대 경로로 저장된 경우 절대 경로로 변환
            if last_group and not os.path.isabs(last_group):
                # 설정은 app.base_dir 기준 상대 경로로 저장되므로, 복원도 동일 기준을 사용
                last_group = os.path.normpath(os.path.join(self.app.base_dir, last_group))

            if last_group and os.path.isfile(last_group):
                self.load_group(path=last_group)

    def _set_dirty(self, dirty=True):
        if self.is_dirty == dirty: return
        self.is_dirty = dirty
        if hasattr(self.app, 'refresh_title'):
            self.app.refresh_title()
        else:
            title = getattr(self.app, 'title_base', '푸크로')
            if dirty: title += '*'
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
                # [상대 경로 처리] 체인 파일 로드 시 절대 경로로 복원
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
        self.log(f"{len(selected_items)}개 항목을 그룹에서 제거했습니다.")
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
            # [상대 경로 처리] 그룹 파일이 있는 폴더 기준으로 상대 경로 저장
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
                # [상대 경로 처리] 로드 시 절대 경로로 복원
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

    # --- [중요] 안정성 개선: UI 업데이트 스레드 안전성 확보 ---
    def update_ui_state(self, playing=None, paused=None):
        """백그라운드 스레드에서 호출되더라도 안전하게 메인 스레드에서 실행합니다."""
        self.after(0, lambda: self._update_ui_state_safe(playing, paused))

    def _update_ui_state_safe(self, playing, paused):
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

        notes_text_widget.insert(tk.END, "푸크로 V4.6 (Stability Update)\n", "title")
        notes_text_widget.insert(tk.END, "주요 개선사항 (V4.6)\n", "subtitle")
        notes_text_widget.insert(tk.END, "• 🚀 [성능] 이미지 캐싱 시스템을 도입하여 검색 속도와 효율을 극대화했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🛡️ [안정성] UI 스레드 처리 로직을 전면 개편하여 '응답 없음' 현상을 방지했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 👁️ [편의성] '항상 위에 표시' 옵션 및 메뉴바를 추가했습니다.\n", "item")

        notes_text_widget.insert(tk.END, "\n이전 변경사항 (V4.5)\n", "subtitle")
        notes_text_widget.insert(tk.END, "• 📝 [도움말] 상세 사용 설명서 내장\n", "item")
        notes_text_widget.insert(tk.END, "• ⌨️ [기능] 단축키 처리 로직 개선\n", "item")

        notes_text_widget.config(state=tk.DISABLED)

class InfoTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self._create_widgets()

    def _create_widgets(self):
        # 개발자 링크
        link_container = tk.Frame(self)
        link_container.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        source_text_label = tk.Label(link_container, text="개발자 블로그 (출처): ")
        source_text_label.pack(side=tk.LEFT, padx=(0, 2))
        url = "https://blog.naver.com/skarbs01/223983468359"
        link_label = tk.Label(link_container, text=url, fg="blue", cursor="hand2")
        link_label.pack(side=tk.LEFT)
        f = tkFont.Font(link_label, link_label.cget("font"))
        f.configure(underline=True)
        link_label.configure(font=f)
        link_label.bind("<Button-1>", lambda e: webbrowser.open_new(url))

        # 도움말 내용
        info_frame = ttk.LabelFrame(self, text="푸크로 (Pucro) 매크로 - 사용 설명서")
        info_frame.pack(fill=tk.BOTH, expand=True)
        help_text = scrolledtext.ScrolledText(info_frame, wrap=tk.WORD, padx=10, pady=10, bd=0, font=("Malgun Gothic", 10))
        help_text.pack(fill=tk.BOTH, expand=True)

        # 스타일 태그 설정
        help_text.tag_configure("h1", font=("Malgun Gothic", 14, "bold"), spacing3=10, foreground="#2c3e50")
        help_text.tag_configure("h2", font=("Malgun Gothic", 12, "bold"), spacing3=5, spacing1=15, foreground="#34495e")
        help_text.tag_configure("h3", font=("Malgun Gothic", 10, "bold"), spacing1=10, foreground="#7f8c8d")
        help_text.tag_configure("bold", font=("Malgun Gothic", 10, "bold"))
        help_text.tag_configure("item", lmargin1=20, lmargin2=20, spacing1=3)
        help_text.tag_configure("code", font=("Consolas", 9), background="#f0f0f0")

        # 매뉴얼 내용 삽입
        help_text.insert(tk.END, "📘 푸크로(Pucro) 매크로 사용 설명서\n", "h1")
        help_text.insert(tk.END, "푸크로는 반복적인 컴퓨터 작업을 자동화해주는 프로그램입니다.\n마우스/키보드 동작을 녹화하거나, 화면의 이미지를 인식하여 클릭하게 할 수 있습니다.\n\n")

        help_text.insert(tk.END, "1. 탭별 기능 소개\n", "h2")
        # ... (기존 내용 생략, 필요시 추가) ...
        help_text.insert(tk.END, "사용 설명서 내용은 블로그를 참고해주세요.\n", "item")

        help_text.config(state=tk.DISABLED)
