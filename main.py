import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import tkinter.font as tkFont
import os
import sys
import json
import time
import re
import threading
import pyautogui
from pynput import keyboard
from ui_components import RecordingMacroTab, ChainGroupTab, ImageMacroTab, InfoTab
from ui.scrollable import ScrollableFrame
from utils import clear_image_cache, is_on_screen

# --- 메인 애플리케이션 클래스 (개선됨) ---
class MainApp:
    def __init__(self, root):
        self.root = root
        self.title_base = "푸크로 V4.8 (Stability Update)"
        self.root.title(self.title_base)
        # [수정] 최소 크기를 화면 크기에 맞춰 결정한다.
        # 고정값(1240x820)은 1366x768 노트북이나 고배율 환경에서 화면보다 커져
        # 창을 줄일 수 없고 아래쪽 UI가 잘려 보이지 않는 원인이 되었다.
        self._apply_min_size()

        # [수정] 설정 파일 경로를 실행 파일 기준 상대 경로(로컬)로 변경 (Portable 지원)
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.config_path = os.path.join(self.base_dir, "pucro_config.json")
        self.config = self.load_config()

        self._apply_theme()
        self.hotkey_listener = None

        # 메뉴바 생성
        self._create_menubar()

        self._create_widgets()
        self._validate_and_set_geometry(self.config.get("geometry"))
        self._setup_hotkeys()

        # 설정 복원 (항상 위에 표시)
        if self.config.get("always_on_top", False):
            self.always_on_top_var.set(True)
            self.toggle_always_on_top()

        # 종료 이벤트 처리
        self.root.protocol("WM_DELETE_WINDOW", self.confirm_and_quit)

    def _create_menubar(self):
        menubar = tk.Menu(self.root)

        # [보기] 메뉴
        view_menu = tk.Menu(menubar, tearoff=0)
        self.always_on_top_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="항상 위에 표시", variable=self.always_on_top_var, command=self.toggle_always_on_top)
        view_menu.add_separator()
        self.theme_var = tk.StringVar(value=self.style.theme_use())

        theme_options = [
            ("clam", "기본 테마 (Clam)"),
            ("alt", "클래식 테마 (Alt)"),
            ("default", "시스템 테마 (Default)"),
            ("vista", "윈도우 테마 (Vista)"),
            ("xpnative", "윈도우 테마 (XP)")
        ]
        for theme_name, theme_label in theme_options:
            if theme_name in self.available_themes:
                view_menu.add_radiobutton(
                    label=theme_label,
                    variable=self.theme_var,
                    value=theme_name,
                    command=self.change_theme
                )
        menubar.add_cascade(label="보기", menu=view_menu)

        # [도구] 메뉴
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="이미지 캐시 초기화", command=self.clear_cache)
        menubar.add_cascade(label="도구", menu=tools_menu)

        self.root.config(menu=menubar)

    def toggle_always_on_top(self):
        is_top = self.always_on_top_var.get()
        self.root.attributes("-topmost", is_top)
        status = "켜짐" if is_top else "꺼짐"
        self.log(f"📌 '항상 위에 표시'가 {status}으로 설정되었습니다.")

    def change_theme(self):
        theme = self.theme_var.get()
        try:
            self.style.theme_use(theme)
            self._apply_soft_ui_style()
            self.log(f"🎨 테마가 '{theme}'로 변경되었습니다.")
        except tk.TclError: pass

    def clear_cache(self):
        clear_image_cache()
        self.log("🧹 이미지 캐시를 수동으로 정리했습니다.")

    def _apply_theme(self):
        """테마 및 스타일 설정"""
        self.style = ttk.Style(self.root)
        self.available_themes = set(self.style.theme_names())

        preferred_theme = None
        if sys.platform == "win32" and "vista" in self.available_themes:
            preferred_theme = "vista"
        elif "clam" in self.available_themes:
            preferred_theme = "clam"
        elif "default" in self.available_themes:
            preferred_theme = "default"

        if preferred_theme:
            try:
                self.style.theme_use(preferred_theme)
            except tk.TclError:
                pass

        self._apply_soft_ui_style()

    def _apply_soft_ui_style(self):
        """둥글고 부드러운 느낌의 공통 스타일을 적용합니다."""
        def _cfg(style_name, **kwargs):
            try:
                self.style.configure(style_name, **kwargs)
            except tk.TclError:
                pass

        def _map(style_name, **kwargs):
            try:
                self.style.map(style_name, **kwargs)
            except tk.TclError:
                pass

        colors = {
            "bg": "#e7eef9",
            "surface": "#ffffff",
            "surface_soft": "#f2f7ff",
            "border": "#b9c9df",
            "text": "#0f2036",
            "muted": "#334a66",
            "accent": "#1859bf",
            "accent_soft": "#e1ecff",
            "accent_hover": "#3c7ced",
            "accent_press": "#1d56b8",
            "danger": "#d84f59",
            "danger_soft": "#fde7eb",
            "danger_hover": "#e36570",
            "danger_press": "#be424c",
            "neutral": "#dee8f8",
            "neutral_hover": "#d2e0f3",
            "neutral_press": "#c7d6ea"
        }
        fonts = {
            "base": ("Malgun Gothic", 12),
            "small": ("Malgun Gothic", 11),
            "button": ("Malgun Gothic", 12, "bold"),
            "label_bold": ("Malgun Gothic", 12, "bold"),
            "tab": ("Malgun Gothic", 12, "bold"),
            "tree": ("Malgun Gothic", 11),
            "tree_heading": ("Malgun Gothic", 11, "bold"),
            "log": ("Malgun Gothic", 11)
        }
        self.ui_theme = {"colors": colors, "fonts": fonts}

        try:
            self.root.configure(bg=colors["bg"])
        except tk.TclError:
            pass

        _cfg(".", font=fonts["base"], background=colors["bg"], foreground=colors["text"])
        _cfg("App.TFrame", background=colors["bg"])
        _cfg("TFrame", background=colors["bg"])
        _cfg("TLabel", font=fonts["base"], background=colors["bg"], foreground=colors["text"])
        _cfg("Link.TLabel", background=colors["bg"], foreground=colors["accent"])
        _cfg("InfoAccent.TLabel", background=colors["surface_soft"], foreground=colors["accent"])
        _cfg("Muted.TLabel", background=colors["surface_soft"], foreground=colors["muted"])

        _cfg("Status.TLabel", font=fonts["small"], background=colors["surface_soft"], foreground=colors["muted"], padding=(12, 6))

        _cfg("TButton", font=fonts["button"], padding=(13, 9), borderwidth=1, relief="flat",
             background=colors["neutral"], foreground=colors["text"])
        _map("TButton",
             background=[("active", colors["neutral_hover"]), ("pressed", colors["neutral_press"])],
             foreground=[("disabled", "#5f728a")])

        _cfg("Accent.TButton", font=fonts["button"], padding=(13, 9), borderwidth=1, relief="flat",
             background=colors["accent_soft"], foreground="#0f468f")
        _map("Accent.TButton",
             background=[("active", "#d5e4ff"), ("pressed", "#cadeff")],
             foreground=[("active", "#0b3f83"), ("pressed", "#09366f"), ("disabled", "#667b99")])

        _cfg("Danger.TButton", font=fonts["button"], padding=(13, 9), borderwidth=1, relief="flat",
             background=colors["danger_soft"], foreground="#b13f48")
        _map("Danger.TButton",
             background=[("active", "#f9dde2"), ("pressed", "#f4d1d7")],
             foreground=[("active", "#9f323c"), ("pressed", "#842a32"), ("disabled", "#9d8a8f")])

        _cfg("Neutral.TButton", font=fonts["button"], padding=(13, 9), borderwidth=1, relief="flat",
             background=colors["neutral"], foreground=colors["text"])
        _map("Neutral.TButton",
             background=[("active", colors["neutral_hover"]), ("pressed", colors["neutral_press"])],
             foreground=[("disabled", "#5f728a")])

        _cfg("Ghost.TButton", font=fonts["button"], padding=(11, 8), borderwidth=1, relief="flat",
             background=colors["surface"], foreground="#23364d")
        _map("Ghost.TButton",
             background=[("active", colors["surface_soft"]), ("pressed", colors["neutral"])],
             foreground=[("disabled", "#5f728a")])

        _cfg("TMenubutton", padding=(10, 6), borderwidth=0)
        _cfg("TCheckbutton", font=fonts["base"], padding=4)
        _cfg("TRadiobutton", font=fonts["base"], padding=4)
        _cfg("TEntry", font=fonts["base"], padding=7, fieldbackground=colors["surface"], foreground=colors["text"])
        _cfg("TCombobox", font=fonts["base"], padding=7, fieldbackground=colors["surface"], foreground=colors["text"])

        _cfg("TLabelframe", padding=10, borderwidth=1, relief="solid", background=colors["bg"])
        _cfg("TLabelframe.Label", font=fonts["label_bold"],
             foreground=colors["muted"], background=colors["bg"])
        _cfg("Card.TLabelframe", padding=14, borderwidth=1, relief="solid", background=colors["surface_soft"])
        _cfg("Card.TLabelframe.Label", font=fonts["label_bold"],
             foreground=colors["muted"], background=colors["surface_soft"])

        _cfg("Soft.TNotebook", background=colors["bg"], borderwidth=0, padding=3)
        _cfg("Soft.TNotebook.Tab", padding=(20, 11), font=fonts["tab"],
             background=colors["neutral"], foreground=colors["muted"])
        _map("Soft.TNotebook.Tab",
             background=[("selected", colors["surface"]), ("active", colors["neutral_hover"])],
             foreground=[("selected", colors["text"]), ("active", colors["text"])])

        # [수정] 행 높이를 픽셀로 고정하면 디스플레이 배율이 높을 때 글자가 잘린다.
        # 실제 글자 높이를 재서 행 높이를 정한다.
        try:
            tree_line_height = tkFont.Font(font=fonts["tree"]).metrics("linespace")
        except tk.TclError:
            tree_line_height = 20
        row_height = max(34, tree_line_height + 14)

        _cfg("Treeview", rowheight=row_height, font=fonts["tree"], background=colors["surface"], fieldbackground=colors["surface"],
             foreground=colors["text"], borderwidth=0)
        _map("Treeview",
             background=[("selected", "#c3d7fb")],
             foreground=[("selected", colors["text"])])
        _cfg("Treeview.Heading", font=fonts["tree_heading"], padding=(8, 7),
             background=colors["neutral"], foreground=colors["muted"])

    def _usable_screen_size(self):
        """작업표시줄 등을 제외한 대략적인 사용 가능 화면 크기."""
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
        except tk.TclError:
            return 1024, 700
        # 작업표시줄/창 테두리 여유
        return max(640, screen_w - 40), max(480, screen_h - 90)

    def _apply_min_size(self):
        usable_w, usable_h = self._usable_screen_size()
        min_w = min(1100, usable_w)
        min_h = min(700, usable_h)
        self.root.minsize(min_w, min_h)
        return min_w, min_h

    def _validate_and_set_geometry(self, geometry):
        usable_w, usable_h = self._usable_screen_size()
        width = min(1320, usable_w)
        height = min(880, usable_h)

        if not geometry:
            self.center_window(width, height)
            return
        try:
            match = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geometry)
            if match:
                w, h, x, y = map(int, match.groups())
                # [수정] 판정을 가상 데스크톱 기준으로 변경.
                # pyautogui.onScreen()은 주 모니터만 인정하므로 보조 모니터에
                # 두었던 창이 매번 주 모니터 중앙으로 끌려오는 문제가 있었다.
                if is_on_screen(x, y):
                    # 저장된 크기가 현재 화면보다 크면 화면에 맞춰 줄인다.
                    w = min(w, usable_w)
                    h = min(h, usable_h)
                    self.root.geometry(f'{w}x{h}+{x}+{y}')
                    return
                else:
                    self.log_event("⚠️ 저장된 창 위치가 화면 밖이라 중앙으로 재설정합니다.")
            self.center_window(width, height)
        except Exception:
            self.center_window(width, height)

    def center_window(self, width, height):
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width // 2) - (width // 2))
        y = max(0, (screen_height // 2) - (height // 2))
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"설정 파일 로드 오류: {e}")
        return {}

    def save_config(self):
        try:
            # 창이 정상 상태일 때만 위치 저장
            if self.root.state() == 'normal':
                self.config['geometry'] = self.root.geometry()

            # [수정] 경로를 상대 경로로 변환하여 저장 (이식성 향상)
            def to_rel(path):
                if not path: return path
                try:
                    # 드라이브가 다르면 상대 경로 변환이 불가능하므로 원래 경로 반환
                    return os.path.relpath(path, self.base_dir)
                except ValueError:
                    return path

            self.config.update({
                "image_tab": {"last_folder": to_rel(self.image_tab.image_folder_path.get())},
                "record_tab": {"last_chain": to_rel(self.recording_tab.current_chain_path)},
                "group_tab": {"last_group": to_rel(self.group_tab.current_group_path)},
                "last_tab_index": self.notebook.index(self.notebook.select()),
                "always_on_top": self.always_on_top_var.get()
            })
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except (IOError, tk.TclError) as e:
            print(f"설정 파일 저장 오류: {e}")

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="8", style="App.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 좌우 분할 (탭 화면 / 로그 화면)
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        self._pane_user_adjusted = False
        self.root.after(120, lambda: self._set_initial_pane_layout(paned_window))
        paned_window.bind('<Configure>', lambda e: self._ensure_pane_min_width(paned_window))
        paned_window.bind('<ButtonPress-1>', lambda e: self._on_pane_press(e, paned_window))

        # [왼쪽] 탭 컨트롤
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=2)
        self.notebook = ttk.Notebook(left_frame, style="Soft.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5, padx=(0, 6))

        # [오른쪽] 로그 화면
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        self._create_log_widgets(right_frame)

        # 하단 상태바
        self.status_var = tk.StringVar(value="준비")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, anchor=tk.W, style="Status.TLabel")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 탭 생성 및 추가
        self._init_tabs()
        self.refresh_title()

        # 마지막 탭 복원
        try:
            last_tab_index = int(self.config.get("last_tab_index", 0))
            if last_tab_index < len(self.notebook.tabs()):
                self.notebook.select(last_tab_index)
        except (ValueError, IndexError):
            self.notebook.select(0)

        self.log("프로그램 준비 완료. 사용할 탭을 선택하고 시작하세요.")

    def _needed_tab_width(self):
        """탭 내용이 가로로 잘리지 않는 데 필요한 폭."""
        needed = 0
        for child in self.notebook.winfo_children():
            inner = getattr(child, 'interior', child)
            try:
                needed = max(needed, inner.winfo_reqwidth())
            except tk.TclError:
                pass
        return needed + 40  # 스크롤바 및 여백

    def _set_initial_pane_layout(self, paned_window):
        try:
            total_width = paned_window.winfo_width()
            if total_width <= 400:
                return

            # [수정] 비율만으로 나누면 창이 좁을 때 왼쪽 탭이 가로로 잘려
            # 버튼과 글자가 보이지 않는다. 탭 내용에 필요한 폭을 우선 확보하되,
            # 로그 영역도 최소 폭을 유지한다.
            target = max(int(total_width * 0.61), self._needed_tab_width())
            target = min(target, max(int(total_width * 0.5), total_width - 300))
            paned_window.sashpos(0, target)
        except tk.TclError:
            pass

    def _on_pane_press(self, event, paned_window):
        """사용자가 분할선을 직접 조절했으면 이후 자동 조정을 멈춘다."""
        try:
            element = paned_window.identify(event.x, event.y)
            # identify()는 sash를 눌렀을 때 인덱스를 돌려주는데, 첫 sash는 정수 0이라
            # 참/거짓으로 검사하면 눌러도 감지되지 않는다. 빈 값인지로 판정한다.
            if element != '' and element is not None:
                self._pane_user_adjusted = True
        except tk.TclError:
            pass

    def _ensure_pane_min_width(self, paned_window):
        """창 크기가 바뀌어도 왼쪽 탭이 가로로 잘리지 않도록 분할선을 보정."""
        if getattr(self, '_pane_user_adjusted', False):
            return
        try:
            total_width = paned_window.winfo_width()
            if total_width <= 400:
                return
            current = paned_window.sashpos(0)
            target = max(current, self._needed_tab_width())
            target = min(target, max(int(total_width * 0.5), total_width - 300))
            # 되먹임으로 인한 반복 조정을 막기 위해 유의미한 차이일 때만 적용
            if abs(target - current) > 2:
                paned_window.sashpos(0, target)
        except tk.TclError:
            pass

    def _create_log_widgets(self, parent):
        theme = getattr(self, "ui_theme", {})
        colors = theme.get("colors", {})
        fonts = theme.get("fonts", {})
        text_bg = colors.get("surface", "#ffffff")
        text_fg = colors.get("text", "#2a3a4d")
        text_border = colors.get("border", "#d7e1ef")
        text_font = fonts.get("log", ("Malgun Gothic", 10))

        log_container = ttk.Frame(parent, style="App.TFrame")
        log_container.pack(fill=tk.BOTH, expand=True, pady=5, padx=(5, 0))
        log_container.columnconfigure(0, weight=1)
        log_container.rowconfigure(1, weight=1)

        # 이벤트 로그
        event_log_frame = ttk.LabelFrame(log_container, text="이벤트 로그", style="Card.TLabelframe")
        event_log_frame.grid(row=0, column=0, sticky='ew')
        event_log_frame.columnconfigure(0, weight=1)
        self.event_log_text = scrolledtext.ScrolledText(
            event_log_frame, wrap=tk.WORD, height=8, state=tk.DISABLED, bd=0,
            font=text_font, padx=11, pady=9,
            bg=text_bg, fg=text_fg, insertbackground=text_fg,
            relief=tk.FLAT, highlightthickness=1, highlightbackground=text_border,
            spacing1=3, spacing3=3
        )
        self.event_log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 실행 로그
        run_log_frame = ttk.LabelFrame(log_container, text="실행 로그", style="Card.TLabelframe")
        run_log_frame.grid(row=1, column=0, sticky='nsew', pady=(5,0))
        run_log_frame.columnconfigure(0, weight=1)
        run_log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            run_log_frame, wrap=tk.WORD, state=tk.DISABLED, bd=0,
            font=text_font, padx=11, pady=9,
            bg=text_bg, fg=text_fg, insertbackground=text_fg,
            relief=tk.FLAT, highlightthickness=1, highlightbackground=text_border,
            spacing1=3, spacing3=3
        )
        self.log_text.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        ttk.Button(run_log_frame, text="로그 지우기", style="Ghost.TButton", command=self.clear_log).grid(row=1, column=0, sticky='e', padx=5, pady=(0,5))

    def _init_tabs(self):
        # [수정] 각 탭을 스크롤 가능한 컨테이너로 감싼다.
        # 화면이 작거나 배율이 높으면 탭 내용(요구 높이 약 1000px 이상)이 창을 넘어
        # 재생 설정·버튼이 잘려 보이지 않았다.
        tab_record = ScrollableFrame(self.notebook)
        tab_group = ScrollableFrame(self.notebook)
        tab_image = ScrollableFrame(self.notebook)
        tab_info = ttk.Frame(self.notebook)   # 도움말은 자체 스크롤 텍스트를 사용

        self.notebook.add(tab_record, text="매크로 체인")
        self.notebook.add(tab_group, text="매크로 그룹")
        self.notebook.add(tab_image, text="이미지 매크로")
        self.notebook.add(tab_info, text="도움말")

        # 각 탭 인스턴스 생성
        # config는 load_config()에서 읽은 raw 딕셔너리.
        # 각 탭 내부에서 상대 경로를 절대 경로로 변환하는 로직 수행 필요.
        self.recording_tab = RecordingMacroTab(tab_record.interior, self, config=self.config.get('record_tab'))
        self.recording_tab.pack(fill=tk.BOTH, expand=True)

        self.group_tab = ChainGroupTab(tab_group.interior, self, config=self.config.get('group_tab'))
        self.group_tab.pack(fill=tk.BOTH, expand=True)

        self.image_tab = ImageMacroTab(tab_image.interior, self, config=self.config.get('image_tab'))
        self.image_tab.pack(fill=tk.BOTH, expand=True)

        self.info_tab = InfoTab(tab_info)
        self.info_tab.pack(fill=tk.BOTH, expand=True)

        # 단축키 처리를 위해 탭 컨테이너 -> 탭 인스턴스 매핑을 보관한다.
        # (스크롤 컨테이너를 씌우면서 winfo_children()[0] 방식은 더 이상 통하지 않음)
        self._tab_instances = {
            str(tab_record): self.recording_tab,
            str(tab_group): self.group_tab,
            str(tab_image): self.image_tab,
            str(tab_info): self.info_tab,
        }

    def _setup_hotkeys(self):
        try:
            self.hotkey_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
            self.hotkey_listener.start()
            self.log("전역 단축키 활성화. (활성 탭에 따라 동작)")
        except Exception as e:
            self.log(f"🔥 단축키 설정 실패: {e}")
            self.log("ℹ️ 관리자 권한으로 실행하거나 접근성 권한을 확인하세요.")

    def refresh_execution_state(self):
        """전역 실행 상태에 맞춰 모든 탭의 시작 버튼을 갱신합니다.

        마우스·키보드를 공유하므로 한 작업이 실행 중이면 다른 탭의 시작도 막는다.
        """
        for name in ('recording_tab', 'group_tab', 'image_tab'):
            tab = getattr(self, name, None)
            if tab is None:
                continue
            refresh = getattr(tab, 'refresh_busy_state', None)
            if refresh is None:
                continue
            try:
                refresh()
            except tk.TclError:
                pass

    def _get_active_tab_widget(self):
        """현재 활성화된 탭의 위젯 인스턴스를 반환"""
        current_tab_id = self.notebook.select()
        if not current_tab_id:
            return None
        return getattr(self, '_tab_instances', {}).get(str(current_tab_id))

    def _on_key_press(self, key):
        try:
            if not self.root.winfo_exists(): return
            # 1. 녹화 중일 때의 우선 처리 (F2/ESC: 중지)
            if self.recording_tab.macro.is_recording:
                # 녹화 중지 키는 기록되지 않도록 여기서 먼저 처리합니다.
                if key in (keyboard.Key.f2, keyboard.Key.esc):
                    self.root.after(0, self.recording_tab.record_stop_button.invoke)
                return

            # 2. 현재 활성 탭에 따른 분기 처리
            active_tab = self._get_active_tab_widget()

            if isinstance(active_tab, RecordingMacroTab):
                if key == keyboard.Key.f1: self.root.after(0, self.recording_tab.record_start_button.invoke)
                elif key == keyboard.Key.f2: self.root.after(0, self.recording_tab.record_stop_button.invoke)
                elif key == keyboard.Key.f3: self.root.after(0, self.recording_tab.play_start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.recording_tab.play_stop_button.invoke)
                elif key == keyboard.Key.f5: self.root.after(0, self.recording_tab.pause_play_button.invoke)

            elif isinstance(active_tab, ChainGroupTab):
                if key == keyboard.Key.f3: self.root.after(0, self.group_tab.play_start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.group_tab.play_stop_button.invoke)
                elif key == keyboard.Key.f5: self.root.after(0, self.group_tab.pause_play_button.invoke)

            elif isinstance(active_tab, ImageMacroTab):
                if key == keyboard.Key.f3: self.root.after(0, self.image_tab.start_button.invoke)
                elif key == keyboard.Key.f4: self.root.after(0, self.image_tab.stop_button.invoke)
                elif key == keyboard.Key.f5: self.root.after(0, self.image_tab.pause_button.invoke)
                # 버튼을 거쳐야 실행 중 잠금(비활성 버튼은 invoke가 무시됨)이 단축키에도 적용된다.
                elif key == keyboard.Key.f9: self.root.after(0, self.image_tab.set_area_button.invoke)

        except Exception:
            pass
    def _on_key_release(self, key):
        """키 릴리즈 이벤트 콜백.

        NOTE: RecordingMacro는 자체 pynput 리스너로 on_release를 기록합니다.
        여기서 다시 전달하면 KEY_UP 이벤트가 2번 기록될 수 있어 중복을 방지합니다.
        """
        return

    def confirm_and_quit(self):
        """종료 전 확인 및 정리"""
        # 실행/녹화 중에는 오동작(입력 중단, 데이터 유실) 가능성이 있어 종료 전 확인
        if (
                self.image_tab.macro.is_running
                or self.recording_tab.macro.is_playing
                or self.recording_tab.macro.is_recording
                or self.group_tab.macro.is_playing
                or self._is_area_selection_active()
        ):
            if not messagebox.askyesno("종료 확인", "매크로가 실행 중이거나 녹화 중입니다. 정말로 종료하시겠습니까?"):
                return

        if self.recording_tab.is_dirty or self.group_tab.is_dirty:
            if not messagebox.askyesno("종료 확인", "저장되지 않은 변경사항이 있습니다. 저장하지 않고 종료하시겠습니까?"):
                return

        self.quit_app()

    def _is_area_selection_active(self):
        """이미지 탭의 화면 영역 선택이 진행 중인지 확인합니다."""
        selector = getattr(getattr(self, 'image_tab', None), 'area_selector', None)
        try:
            return bool(selector and selector.is_alive())
        except Exception:
            return False

    def quit_app(self):
        """애플리케이션 안전 종료"""
        if hasattr(self, 'image_tab'):
            self.image_tab.macro.stop()
            # 영역 선택 중이면 전역 마우스/키보드 리스너를 명시적으로 중지한다.
            selector = getattr(self.image_tab, 'area_selector', None)
            if selector is not None:
                try:
                    selector.cleanup()
                except Exception:
                    pass
        if hasattr(self, 'recording_tab'):
            self.recording_tab.macro.stop_playback()
            self.recording_tab.macro.stop_recording()
        if hasattr(self, 'group_tab'): self.group_tab.macro.stop_playback()

        # 이미지 캐시 정리
        clear_image_cache()

        if self.hotkey_listener and self.hotkey_listener.is_alive():
            self.hotkey_listener.stop()

        self.save_config()
        self.root.destroy()
        sys.exit(0)

    # --- 유틸리티 메서드 ---
    def update_tree_selection(self, tree, item_id):
        try:
            if tree.exists(item_id):
                tree.selection_set(item_id)
                tree.focus(item_id)
                tree.see(item_id)
        except tk.TclError: pass

    def log(self, message):
        self.root.after(0, self._log_update, self.log_text, message)

    def log_event(self, message):
        self.root.after(0, self._log_update, self.event_log_text, message)

    def _log_update(self, text_widget, message):
        try:
            if not text_widget.winfo_exists(): return
            text_widget.config(state=tk.NORMAL)
            text_widget.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
            text_widget.see(tk.END)
            text_widget.config(state=tk.DISABLED)
        except tk.TclError: pass

    def clear_log(self):
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log("로그 창을 초기화했습니다.")
        except tk.TclError: pass

    def refresh_title(self):
        title = self.title_base
        has_dirty = False
        if hasattr(self, 'recording_tab') and getattr(self.recording_tab, 'is_dirty', False):
            has_dirty = True
        if hasattr(self, 'group_tab') and getattr(self.group_tab, 'is_dirty', False):
            has_dirty = True
        if has_dirty:
            title += '*'
        try:
            self.root.title(title)
        except tk.TclError:
            pass

    def update_status(self, message):
        try:
            if threading.current_thread() is threading.main_thread():
                self.status_var.set(message)
            else:
                self.root.after(0, self.status_var.set, message)
        except (tk.TclError, RuntimeError):
            pass

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass

    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()
