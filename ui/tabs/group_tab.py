import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
from constants import RepeatMode, MacroType
from macro_logic import ChainGroupMacro

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
        play_frame = ttk.LabelFrame(top_frame, text="재생", style="Card.TLabelframe")
        play_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0,5))
        play_frame.columnconfigure(0, weight=1)
        self.play_start_button = ttk.Button(play_frame, text="그룹 재생 시작 (F3)", style="Accent.TButton", command=self.start_group_playback)
        self.play_start_button.pack(fill=tk.X, padx=5, pady=5)
        self.pause_play_button = ttk.Button(play_frame, text="일시정지 (F5)", style="Neutral.TButton", command=self.macro.pause_or_resume_playback, state=tk.DISABLED)
        self.pause_play_button.pack(fill=tk.X, padx=5, pady=5)
        self.play_stop_button = ttk.Button(play_frame, text="그룹 재생 중지 (F4)", style="Danger.TButton", command=self.macro.stop_playback, state=tk.DISABLED)
        self.play_stop_button.pack(fill=tk.X, padx=5, pady=5)
        group_io_frame = ttk.LabelFrame(top_frame, text="그룹 파일", style="Card.TLabelframe")
        group_io_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(5,0))
        self.load_group_button = ttk.Button(group_io_frame, text="불러오기", style="Ghost.TButton", command=self.load_group)
        self.load_group_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_group_button = ttk.Button(group_io_frame, text="저장", style="Ghost.TButton", command=self.save_group)
        self.save_group_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_as_group_button = ttk.Button(group_io_frame, text="다른 이름으로...", style="Ghost.TButton", command=lambda: self.save_group(save_as=True))
        self.save_as_group_button.pack(fill=tk.X, padx=5, pady=5)
        playlist_frame = ttk.LabelFrame(self, text="매크로 그룹 편집기 (체인 재생 목록)", style="Card.TLabelframe")
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
        ttk.Button(btn_frame, text="체인 추가", style="Accent.TButton", command=self.add_chain_to_list).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="제거", style="Ghost.TButton", command=self.remove_selected_chain).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="▲", style="Ghost.TButton", command=self.move_chain_up).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="▼", style="Ghost.TButton", command=self.move_chain_down).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="모두 삭제", style="Danger.TButton", command=self.clear_chain_list).pack(fill=tk.X, pady=2)
        self.play_settings_frame = ttk.LabelFrame(self, text="재생 설정 (전체 그룹)", style="Card.TLabelframe")
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
                if hasattr(child, 'config'):
                    try:
                        child.config(state=state)
                    except tk.TclError:
                        pass
            self.toggle_repeat_entry()
            if paused is not None:
                self.pause_play_button.config(text="재개 (F5)" if paused else "일시정지 (F5)")
        except tk.TclError: pass
