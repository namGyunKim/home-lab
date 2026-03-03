import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import sys
import json
import time
import re
import threading
import pyautogui
from pynput import keyboard
from ui_components import RecordingMacroTab, ChainGroupTab, ImageMacroTab, PatchNotesTab, InfoTab
from utils import clear_image_cache

# --- 메인 애플리케이션 클래스 (개선됨) ---
class MainApp:
    def __init__(self, root):
        self.root = root
        self.title_base = "푸크로 V4.6 (Stability Update)"
        self.root.title(self.title_base)

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
        self.theme_var = tk.StringVar(value="clam")
        view_menu.add_radiobutton(label="기본 테마 (Clam)", variable=self.theme_var, value="clam", command=self.change_theme)
        view_menu.add_radiobutton(label="클래식 테마 (Alt)", variable=self.theme_var, value="alt", command=self.change_theme)
        view_menu.add_radiobutton(label="시스템 테마 (Default)", variable=self.theme_var, value="default", command=self.change_theme)
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
            self.log(f"🎨 테마가 '{theme}'로 변경되었습니다.")
        except tk.TclError: pass

    def clear_cache(self):
        clear_image_cache()
        self.log("🧹 이미지 캐시를 수동으로 정리했습니다.")

    def _apply_theme(self):
        """테마 및 스타일 설정"""
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            print("'clam' 테마를 찾을 수 없습니다. 기본 테마로 실행합니다.")

        self.style.configure("Treeview.Heading", font=(None, 10, 'bold'))
        self.style.configure("TButton", padding=5)
        self.style.configure("TMenubutton", padding=5)

    def _validate_and_set_geometry(self, geometry):
        width, height = 1100, 750
        if not geometry:
            self.center_window(width, height)
            return
        try:
            match = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geometry)
            if match:
                w, h, x, y = map(int, match.groups())
                if pyautogui.onScreen(x, y):
                    self.root.geometry(geometry)
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
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
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
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 좌우 분할 (탭 화면 / 로그 화면)
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        # [왼쪽] 탭 컨트롤
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=2)
        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5, padx=(0, 5))

        # [오른쪽] 로그 화면
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        self._create_log_widgets(right_frame)

        # 하단 상태바
        self.status_var = tk.StringVar(value="준비")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
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

    def _create_log_widgets(self, parent):
        log_container = ttk.Frame(parent)
        log_container.pack(fill=tk.BOTH, expand=True, pady=5, padx=(5, 0))
        log_container.columnconfigure(0, weight=1)
        log_container.rowconfigure(1, weight=1)

        # 이벤트 로그
        event_log_frame = ttk.LabelFrame(log_container, text="이벤트 로그")
        event_log_frame.grid(row=0, column=0, sticky='ew')
        event_log_frame.columnconfigure(0, weight=1)
        self.event_log_text = scrolledtext.ScrolledText(event_log_frame, wrap=tk.WORD, height=8, state=tk.DISABLED, bd=0)
        self.event_log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 실행 로그
        run_log_frame = ttk.LabelFrame(log_container, text="실행 로그")
        run_log_frame.grid(row=1, column=0, sticky='nsew', pady=(5,0))
        run_log_frame.columnconfigure(0, weight=1)
        run_log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(run_log_frame, wrap=tk.WORD, state=tk.DISABLED, bd=0)
        self.log_text.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        ttk.Button(run_log_frame, text="로그 지우기", command=self.clear_log).grid(row=1, column=0, sticky='e', padx=5, pady=(0,5))

    def _init_tabs(self):
        # 탭 컨테이너 생성
        tab_record = ttk.Frame(self.notebook)
        tab_group = ttk.Frame(self.notebook)
        tab_image = ttk.Frame(self.notebook)
        tab_patch = ttk.Frame(self.notebook)
        tab_info = ttk.Frame(self.notebook)

        self.notebook.add(tab_record, text="  매크로 체인  ")
        self.notebook.add(tab_group, text="  매크로 그룹  ")
        self.notebook.add(tab_image, text="  이미지 매크로  ")
        self.notebook.add(tab_patch, text="  패치노트  ")
        self.notebook.add(tab_info, text="  도움말  ")

        # 각 탭 인스턴스 생성
        # config는 load_config()에서 읽은 raw 딕셔너리.
        # 각 탭 내부에서 상대 경로를 절대 경로로 변환하는 로직 수행 필요.
        self.recording_tab = RecordingMacroTab(tab_record, self, config=self.config.get('record_tab'))
        self.recording_tab.pack(fill=tk.BOTH, expand=True)

        self.group_tab = ChainGroupTab(tab_group, self, config=self.config.get('group_tab'))
        self.group_tab.pack(fill=tk.BOTH, expand=True)

        self.image_tab = ImageMacroTab(tab_image, self, config=self.config.get('image_tab'))
        self.image_tab.pack(fill=tk.BOTH, expand=True)

        self.patch_notes_tab = PatchNotesTab(tab_patch)
        self.patch_notes_tab.pack(fill=tk.BOTH, expand=True)

        self.info_tab = InfoTab(tab_info)
        self.info_tab.pack(fill=tk.BOTH, expand=True)

    def _setup_hotkeys(self):
        try:
            self.hotkey_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
            self.hotkey_listener.start()
            self.log("전역 단축키 활성화. (활성 탭에 따라 동작)")
        except Exception as e:
            self.log(f"🔥 단축키 설정 실패: {e}")
            self.log("ℹ️ 관리자 권한으로 실행하거나 접근성 권한을 확인하세요.")

    def _get_active_tab_widget(self):
        """현재 활성화된 탭의 위젯 인스턴스를 반환"""
        current_tab_id = self.notebook.select()
        current_widget = self.notebook.nametowidget(current_tab_id)
        if current_widget.winfo_children():
            return current_widget.winfo_children()[0]
        return None

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
                elif key == keyboard.Key.f9: self.root.after(0, self.image_tab.start_defining_area)

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
        ):
            if not messagebox.askyesno("종료 확인", "매크로가 실행 중이거나 녹화 중입니다. 정말로 종료하시겠습니까?"):
                return

        if self.recording_tab.is_dirty or self.group_tab.is_dirty:
            if not messagebox.askyesno("종료 확인", "저장되지 않은 변경사항이 있습니다. 저장하지 않고 종료하시겠습니까?"):
                return

        self.quit_app()

    def quit_app(self):
        """애플리케이션 안전 종료"""
        if hasattr(self, 'image_tab'): self.image_tab.macro.stop()
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
