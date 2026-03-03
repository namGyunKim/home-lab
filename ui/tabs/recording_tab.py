import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
from constants import RepeatMode, MacroType
from macro_logic import RecordingMacro

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
        record_frame = ttk.LabelFrame(top_frame, text="녹화", style="Card.TLabelframe")
        record_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0,5))
        record_frame.columnconfigure(0, weight=1)
        self.record_start_button = ttk.Button(record_frame, text="녹화 시작 (F1)", style="Accent.TButton", command=self.macro.start_recording)
        self.record_start_button.pack(fill=tk.X, padx=5, pady=5)
        self.record_stop_button = ttk.Button(record_frame, text="녹화 중지 (F2)", style="Danger.TButton", command=self.macro.stop_recording, state=tk.DISABLED)
        self.record_stop_button.pack(fill=tk.X, padx=5, pady=5)
        play_frame = ttk.LabelFrame(top_frame, text="재생 (현재 체인)", style="Card.TLabelframe")
        play_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(5,0))
        play_frame.columnconfigure(0, weight=1)
        self.play_start_button = ttk.Button(play_frame, text="재생 시작 (F3)", style="Accent.TButton", command=self.start_macro_chain)
        self.play_start_button.pack(fill=tk.X, padx=5, pady=5)
        self.pause_play_button = ttk.Button(play_frame, text="일시정지 (F5)", style="Neutral.TButton", command=self.macro.pause_or_resume_playback, state=tk.DISABLED)
        self.pause_play_button.pack(fill=tk.X, padx=5, pady=5)
        self.play_stop_button = ttk.Button(play_frame, text="재생 중지 (F4)", style="Danger.TButton", command=self.macro.stop_playback, state=tk.DISABLED)
        self.play_stop_button.pack(fill=tk.X, padx=5, pady=5)
        chain_io_frame = ttk.LabelFrame(top_frame, text="체인 파일", style="Card.TLabelframe")
        chain_io_frame.grid(row=0, column=2, sticky=tk.NSEW, padx=(5,0))
        self.load_chain_button = ttk.Button(chain_io_frame, text="불러오기", style="Ghost.TButton", command=self.load_chain)
        self.load_chain_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_chain_button = ttk.Button(chain_io_frame, text="저장", style="Ghost.TButton", command=self.save_chain)
        self.save_chain_button.pack(fill=tk.X, padx=5, pady=5)
        self.save_as_chain_button = ttk.Button(chain_io_frame, text="다른 이름으로...", style="Ghost.TButton", command=lambda: self.save_chain(save_as=True))
        self.save_as_chain_button.pack(fill=tk.X, padx=5, pady=5)
        playlist_frame = ttk.LabelFrame(self, text="매크로 체인 편집기 (재생 목록)", style="Card.TLabelframe")
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
        add_btn_frame = ttk.LabelFrame(btn_frame, text="추가", style="Card.TLabelframe")
        add_btn_frame.pack(pady=2, fill=tk.X)
        self.add_file_button = ttk.Button(add_btn_frame, text="녹화 파일", style="Ghost.TButton", command=self.add_file_macro_to_list)
        self.add_file_button.pack(fill=tk.X, padx=2, pady=(2,0))
        self.add_wait_image_button = ttk.Button(add_btn_frame, text="이미지 대기", style="Ghost.TButton", command=self.add_wait_image_macro_to_list)
        self.add_wait_image_button.pack(fill=tk.X, padx=2, pady=2)
        edit_btn_frame = ttk.LabelFrame(btn_frame, text="편집", style="Card.TLabelframe")
        edit_btn_frame.pack(pady=(10,2), fill=tk.X)
        self.remove_button = ttk.Button(edit_btn_frame, text="제거", style="Ghost.TButton", command=self.remove_selected_macro)
        self.remove_button.pack(fill=tk.X, padx=2, pady=2)
        self.up_button = ttk.Button(edit_btn_frame, text="▲", style="Ghost.TButton", command=self.move_macro_up)
        self.up_button.pack(fill=tk.X, padx=2, pady=2)
        self.down_button = ttk.Button(edit_btn_frame, text="▼", style="Ghost.TButton", command=self.move_macro_down)
        self.down_button.pack(fill=tk.X, padx=2, pady=2)
        self.clear_button = ttk.Button(edit_btn_frame, text="모두 삭제", style="Danger.TButton", command=self.clear_macro_list)
        self.clear_button.pack(fill=tk.X, padx=2, pady=2)
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)
        self.save_button = ttk.Button(bottom_frame, text="선택 항목 저장", style="Ghost.TButton", command=self.save_selected_macro, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=(0, 10))
        self.test_run_button = ttk.Button(bottom_frame, text="선택 항목 테스트", style="Accent.TButton", command=self.test_run_selected, state=tk.DISABLED)
        self.test_run_button.pack(side=tk.LEFT)
        self.play_settings_frame = ttk.LabelFrame(self, text="재생 설정 (현재 체인)", style="Card.TLabelframe")
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
        help_button = ttk.Button(img_wait_frame, text="?", style="Ghost.TButton", width=2, command=self.show_help)
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
            self.macro_tree.tag_configure('image_wait_macro', foreground='#b55e08')
            self.playlist_data[item_id] = {'type': MacroType.IMAGE_WAIT.value, 'data': file, 'display_name': display_name}
            self.log(f"✅ 이미지(대기) '{os.path.basename(file)}'를 추가했습니다.")
            self._set_dirty()

    def add_memory_macro_to_list(self, actions):
        display_name = f"새 녹화 {self.new_recording_counter}"
        self.new_recording_counter += 1
        item_id = self.macro_tree.insert("", tk.END, values=(display_name, "1.0"), tags=('memory_macro',))
        self.macro_tree.tag_configure('memory_macro', foreground='#1f64d9')
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
            self.macro_tree.tag_configure('memory_macro', foreground='#1f64d9')
            self.macro_tree.tag_configure('image_wait_macro', foreground='#b55e08')
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
                    if btn.winfo_exists():
                        try:
                            btn.config(state=state)
                        except tk.TclError:
                            pass

                if self.play_settings_frame.winfo_exists():
                    for child in self.play_settings_frame.winfo_children():
                        try:
                            child.config(state=state)
                        except tk.TclError:
                            pass
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

