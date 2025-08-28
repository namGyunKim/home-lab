import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
from collections import OrderedDict
from datetime import datetime

# --- 상수 및 설정 ---
DATA_FILE = "guild_data_categorized.json"
WINDOW_TITLE = "길드 재료 기여 현황"
CATEGORIES = OrderedDict([
    ("primary", "1차 재료"),
    ("secondary", "2차 재료"),
    ("tertiary", "3차 재료")
])
LOG_LIMIT = 100 # 최대 로그 저장 개수

# --- 맞춤형 대화상자 ---
class AddMaterialDialog(tk.Toplevel):
    """재료 이름과 수량을 한 번에 입력받는 맞춤형 대화상자 클래스"""
    def __init__(self, parent, title, category_name):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.parent = parent
        self.result = None

        body = ttk.Frame(self, padding="10 10 10 10")
        self.initial_focus = self.body(body, category_name)
        body.pack(padx=5, pady=5)

        self.buttonbox()
        self.grab_set()

        if not self.initial_focus:
            self.initial_focus = self

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.geometry(f"+{parent.winfo_rootx()+50}+{parent.winfo_rooty()+50}")
        self.initial_focus.focus_set()
        self.wait_window(self)

    def body(self, master, category_name):
        ttk.Label(master, text=f"'{category_name}'에 추가할 새 재료 정보를 입력하세요.", font=('Inter', 10, 'bold')).grid(row=0, columnspan=2, pady=(0, 10))
        ttk.Label(master, text="재료 이름:").grid(row=1, sticky="w")
        self.name_entry = ttk.Entry(master, width=30)
        self.name_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(master, text="총 필요 수량:").grid(row=2, sticky="w")
        self.total_entry = ttk.Entry(master, width=30)
        self.total_entry.grid(row=2, column=1, padx=5, pady=5)
        return self.name_entry

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="확인", width=10, command=self.ok, default=tk.ACTIVE).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(box, text="취소", width=10, command=self.cancel).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def ok(self, event=None):
        name = self.name_entry.get().strip()
        total_str = self.total_entry.get().strip()
        if not name:
            messagebox.showwarning("입력 오류", "재료 이름을 입력해야 합니다.", parent=self)
            return
        try:
            total = int(total_str)
            if total < 0: raise ValueError
        except ValueError:
            messagebox.showwarning("입력 오류", "총 필요 수량은 0 이상의 숫자여야 합니다.", parent=self)
            return
        self.result = {"name": name, "total": total}
        self.withdraw()
        self.update_idletasks()
        self.parent.focus_set()
        self.destroy()

    def cancel(self, event=None):
        self.parent.focus_set()
        self.destroy()

class EditContributionDialog(tk.Toplevel):
    """기여도를 더하거나 빼서 수정하는 맞춤형 대화상자 클래스"""
    def __init__(self, parent, title, member, material, current_value):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.parent = parent
        self.result = None
        self.current_value = current_value

        body = ttk.Frame(self, padding="10 10 10 10")
        self.initial_focus = self.body(body, member, material)
        body.pack(padx=5, pady=5)

        self.buttonbox()
        self.grab_set()

        if not self.initial_focus: self.initial_focus = self
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.geometry(f"+{parent.winfo_rootx()+50}+{parent.winfo_rooty()+50}")
        self.initial_focus.focus_set()
        self.wait_window(self)

    def body(self, master, member, material):
        info_text = f"'{member}'님의 '{material}' 기여 수량 수정"
        ttk.Label(master, text=info_text, font=('Inter', 10, 'bold')).grid(row=0, columnspan=3, pady=(0, 10))
        ttk.Label(master, text=f"현재 수량: {self.current_value:,}").grid(row=1, columnspan=3, pady=(0, 10))

        self.operation_var = tk.StringVar(value="+")
        op_frame = ttk.Frame(master)
        ttk.Radiobutton(op_frame, text="+ (더하기)", variable=self.operation_var, value="+").pack(side="left", padx=10)
        ttk.Radiobutton(op_frame, text="- (빼기)", variable=self.operation_var, value="-").pack(side="left", padx=10)
        op_frame.grid(row=2, columnspan=3, pady=5)

        ttk.Label(master, text="수량:").grid(row=3, column=0, sticky="w")
        self.amount_entry = ttk.Entry(master, width=20)
        self.amount_entry.grid(row=3, column=1, columnspan=2, padx=5, pady=5)
        return self.amount_entry

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="적용", width=10, command=self.ok, default=tk.ACTIVE).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(box, text="취소", width=10, command=self.cancel).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def ok(self, event=None):
        amount_str = self.amount_entry.get().strip()
        try:
            amount = int(amount_str)
            if amount < 0: raise ValueError
        except ValueError:
            messagebox.showwarning("입력 오류", "수량은 0 이상의 숫자여야 합니다.", parent=self)
            return

        operation = self.operation_var.get()
        if operation == "+":
            new_total = self.current_value + amount
        else:
            new_total = self.current_value - amount
            if new_total < 0:
                messagebox.showwarning("계산 오류", "계산 결과가 0보다 작을 수 없습니다.", parent=self)
                return
        
        self.result = new_total
        self.withdraw()
        self.update_idletasks()
        self.parent.focus_set()
        self.destroy()

    def cancel(self, event=None):
        self.parent.focus_set()
        self.destroy()

class RankingDialog(tk.Toplevel):
    """카테고리별 납품 랭킹을 보여주는 대화상자 클래스"""
    def __init__(self, parent, title, category_name, ranking_data, materials_in_category):
        super().__init__(parent)
        self.transient(parent)
        self.title(f"{category_name} 납품 랭킹 (헤더 클릭으로 정렬)")
        self.parent = parent
        
        self.ranking_data = ranking_data
        self.materials_in_category = materials_in_category
        self.sort_column = 'total'
        self.sort_reverse = True

        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self._configure_styles()

        self.configure(background='#ffffff')
        body = ttk.Frame(self, padding="10 10 10 10", style='Dialog.TFrame')
        self.body(body, category_name)
        body.pack(padx=5, pady=5, fill="both", expand=True)

        self.buttonbox()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        
        width = 250 + len(materials_in_category) * 90
        screen_width = self.winfo_screenwidth()
        max_width = int(screen_width * 0.8)
        width = min(width, max_width)
        min_width = 400
        width = max(width, min_width)

        self.geometry(f"{width}x500+{parent.winfo_rootx()+100}+{parent.winfo_rooty()+100}")
        self.minsize(min_width, 400)

        self.focus_set()
        self.wait_window(self)

    def _configure_styles(self):
        self.style.configure('Dialog.TFrame', background='#ffffff')
        self.style.configure('DialogHeader.TLabel', background='#ffffff', font=('Inter', 16, 'bold'), foreground='#333')
        self.style.configure('Treeview.Heading', font=('Inter', 10, 'bold'))
        self.style.configure('Treeview', font=('Inter', 10), rowheight=28)

    def body(self, master, category_name):
        ttk.Label(master, text=f"{category_name} 납품 랭킹", style='DialogHeader.TLabel').pack(pady=(0, 15))
        
        tree_frame = ttk.Frame(master, style='Dialog.TFrame')
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(tree_frame, show="headings")
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)

        self._populate_tree()

    def _populate_tree(self):
        for i in self.tree.get_children(): self.tree.delete(i)

        columns = ["rank", "name"] + [f"{cat_key}:{mat['name']}" for mat, cat_key in self.materials_in_category] + ["total"]
        self.tree["columns"] = columns
        
        self.tree.heading("rank", text="순위", command=lambda: self._sort_by("rank"))
        self.tree.heading("name", text="길드원", command=lambda: self._sort_by("name"))
        for mat, cat_key in self.materials_in_category:
            header_text = f"({CATEGORIES[cat_key].replace(' 재료','')}) {mat['name']}"
            composite_key = f"{cat_key}:{mat['name']}"
            self.tree.heading(composite_key, text=header_text, command=lambda k=composite_key: self._sort_by(k))
        self.tree.heading("total", text="총 기여도", command=lambda: self._sort_by("total"))

        self.tree.column("rank", width=60, anchor="center", stretch=False)
        self.tree.column("name", anchor="w", width=120, stretch=False)
        for mat, cat_key in self.materials_in_category:
            self.tree.column(f"{cat_key}:{mat['name']}", anchor="e", width=90)
        self.tree.column("total", anchor="e", width=110, stretch=False)

        if self.sort_column == 'total':
            sorted_data = sorted(self.ranking_data, key=lambda x: x['total'], reverse=self.sort_reverse)
        elif self.sort_column == 'name':
            sorted_data = sorted(self.ranking_data, key=lambda x: x['name'], reverse=self.sort_reverse)
        elif self.sort_column == 'rank':
            sorted_data = sorted(self.ranking_data, key=lambda x: x['total'], reverse=not self.sort_reverse)
        else:
            sorted_data = sorted(self.ranking_data, key=lambda x: x['contributions'].get(self.sort_column, 0), reverse=self.sort_reverse)

        for i, data in enumerate(sorted_data):
            rank_display = f"{i+1}위"
            if i == 0: rank_display = "🥇 " + rank_display
            elif i == 1: rank_display = "🥈 " + rank_display
            elif i == 2: rank_display = "🥉 " + rank_display

            values = [rank_display, data["name"]]
            for mat, cat_key in self.materials_in_category:
                composite_key = f"{cat_key}:{mat['name']}"
                values.append(f"{data['contributions'].get(composite_key, 0):,}")
            values.append(f"{data['total']:,}")
            self.tree.insert("", "end", values=values)

    def _sort_by(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = True if col != 'name' else False
        self._populate_tree()

    def buttonbox(self):
        box = ttk.Frame(self, style='Dialog.TFrame')
        ttk.Button(box, text="닫기", width=10, command=self.cancel).pack(pady=10)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def cancel(self, event=None):
        self.parent.focus_set()
        self.destroy()

# --- ★★★ 새로운 기능: 납품 로그 표시 대화상자 ★★★ ---
class LogDialog(tk.Toplevel):
    """납품 로그를 보여주는 대화상자 클래스"""
    def __init__(self, parent, logs):
        super().__init__(parent)
        self.transient(parent)
        self.title("최근 납품 로그")
        self.parent = parent
        
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('Treeview.Heading', font=('Inter', 10, 'bold'))
        self.style.configure('Treeview', font=('Inter', 10), rowheight=28)

        body = ttk.Frame(self, padding="10 10 10 10")
        self.body(body, logs)
        body.pack(padx=5, pady=5, fill="both", expand=True)

        self.buttonbox()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.geometry(f"650x500+{parent.winfo_rootx()+150}+{parent.winfo_rooty()+150}")
        self.minsize(500, 300)
        self.focus_set()
        self.wait_window(self)

    def _format_relative_time(self, timestamp_str):
        if not timestamp_str: return ""
        log_time = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        delta = now - log_time
        
        seconds = delta.total_seconds()
        if seconds < 60:
            return "방금 전"
        elif seconds < 3600:
            return f"{int(seconds / 60)}분 전"
        elif seconds < 86400:
            return f"{int(seconds / 3600)}시간 전"
        else:
            return f"{int(seconds / 86400)}일 전"

    def body(self, master, logs):
        tree_frame = ttk.Frame(master)
        tree_frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(tree_frame, columns=("time", "member", "material", "change", "result"), show="headings")
        tree.heading("time", text="시간")
        tree.heading("member", text="길드원")
        tree.heading("material", text="재료")
        tree.heading("change", text="변경사항")
        tree.heading("result", text="결과")

        tree.column("time", width=80, anchor="center")
        tree.column("member", width=100, anchor="w")
        tree.column("material", width=150, anchor="w")
        tree.column("change", width=80, anchor="center")
        tree.column("result", width=120, anchor="e")

        for log in reversed(logs): # 최신 로그가 위로 오도록
            relative_time = self._format_relative_time(log.get("timestamp"))
            change = log.get("change", 0)
            change_str = f"+{change:,}" if change > 0 else f"{change:,}"
            result_str = f"{log.get('old_value', 0):,} → {log.get('new_value', 0):,}"
            
            tree.insert("", "end", values=(
                relative_time,
                log.get("member", ""),
                log.get("material_display", ""),
                change_str,
                result_str
            ))

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="닫기", width=10, command=self.cancel).pack(pady=10)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def cancel(self, event=None):
        self.parent.focus_set()
        self.destroy()

class GuildContributionTracker:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')
        self._configure_styles()

        self.manage_category_var = tk.StringVar(value="primary")
        self.view_category_var = tk.StringVar(value="all")
        self.member_search_var = tk.StringVar()
        self.main_table_search_var = tk.StringVar()
        self.sort_column = None
        self.sort_reverse = False
        self.current_display_materials = []

        self.data = self._load_data()
        self._create_widgets()
        self._update_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def _configure_styles(self):
        self.style.configure('TFrame', background='#f0f2f5')
        self.style.configure('TLabel', background='#f0f2f5', font=('Inter', 10))
        self.style.configure('Header.TLabel', font=('Inter', 18, 'bold'), foreground='#333')
        self.style.configure('TimestampBody.TLabel', background='#f0f2f5', font=('Inter', 10), foreground='#555')
        self.style.configure('TLabelframe', background='#f0f2f5', borderwidth=1)
        self.style.configure('TLabelframe.Label', background='#f0f2f5', font=('Inter', 12, 'bold'), foreground='#555')
        self.style.configure('TButton', font=('Inter', 10), padding=6)
        self.style.configure('TRadiobutton', background='#f0f2f5', font=('Inter', 10))
        self.style.configure('Treeview', font=('Inter', 10), rowheight=28)
        self.style.configure('Treeview.Heading', font=('Inter', 10, 'bold'))
        self.style.configure('total_row.Treeview', font=('Inter', 10, 'bold'), background='#e8eaf6')
        self.style.configure('oddrow.Treeview', background='#ffffff')
        self.style.configure('evenrow.Treeview', background='#f7f9fc')

    def _load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if self._migration_needed(data):
                        messagebox.showinfo("데이터 구조 업데이트", "기존 데이터를 새로운 형식으로 변환합니다. 변환 후 데이터가 자동으로 저장됩니다.")
                        data = self._migrate_data_structure(data)
                        with open(DATA_FILE, 'w', encoding='utf-8') as wf:
                            json.dump(data, wf, indent=4, ensure_ascii=False)
                    # 로그 필드 확인 및 추가
                    if "logs" not in data:
                        data["logs"] = []
                    return data
            except (IOError, json.JSONDecodeError) as e:
                messagebox.showerror("오류", f"데이터 로딩 실패: {e}")
                return self._get_default_data()
        else:
            return self._get_default_data()

    def _migration_needed(self, data):
        if not data.get('members'):
            return False
        first_member_contributions = data['members'][0].get('contributions', {})
        if not first_member_contributions:
            return False
        return not any(':' in key for key in first_member_contributions)

    def _migrate_data_structure(self, data):
        material_map = {}
        for cat_key, materials in data.get('materials', {}).items():
            for mat in materials:
                if mat['name'] not in material_map:
                    material_map[mat['name']] = []
                material_map[mat['name']].append(cat_key)

        for member in data.get('members', []):
            old_contributions = member.get('contributions', {})
            new_contributions = {}
            for name, value in old_contributions.items():
                if name in material_map:
                    for i, cat_key in enumerate(material_map[name]):
                        composite_key = f"{cat_key}:{name}"
                        new_contributions[composite_key] = value if i == 0 else 0
            member['contributions'] = new_contributions
        
        data["last_updated"] = {"members": None, "materials": None}
        data["logs"] = [] # 로그 필드 초기화
        return data

    def _get_default_data(self):
        return {
            "materials": { "primary": [], "secondary": [], "tertiary": [] },
            "members": [],
            "last_updated": { "members": None, "materials": None },
            "logs": []
        }

    def _save_data(self, update_type):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if update_type in self.data["last_updated"]:
            self.data["last_updated"][update_type] = now
        
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            messagebox.showerror("오류", f"데이터 저장 실패: {e}")
        
        self._update_timestamp_display()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10 10 10 10")
        main_frame.pack(expand=True, fill="both")
        
        header_frame = ttk.Frame(main_frame, padding="0 0 0 10")
        header_frame.pack(fill="x")
        ttk.Label(header_frame, text=WINDOW_TITLE, style='Header.TLabel').pack(side="left", anchor='w')
        
        timestamp_frame = ttk.Frame(header_frame)
        timestamp_frame.pack(side="right")
        self.materials_updated_label = ttk.Label(timestamp_frame, text="", style='TimestampBody.TLabel', anchor='e')
        self.materials_updated_label.pack(fill='x')
        self.members_updated_label = ttk.Label(timestamp_frame, text="", style='TimestampBody.TLabel', anchor='e')
        self.members_updated_label.pack(fill='x')

        paned_window = ttk.PanedWindow(main_frame, orient='horizontal')
        paned_window.pack(fill='both', expand=True, pady=10)

        left_pane = ttk.Frame(paned_window, padding=10)
        paned_window.add(left_pane, weight=1)

        mat_frame = ttk.LabelFrame(left_pane, text="재료 관리", padding="10")
        mat_frame.pack(fill="x", pady=(0, 10))
        mat_cat_frame = ttk.Frame(mat_frame)
        mat_cat_frame.pack(fill="x", pady=(0, 10))
        for key, text in CATEGORIES.items():
            ttk.Radiobutton(mat_cat_frame, text=text, variable=self.manage_category_var, value=key, command=self._update_material_listbox).pack(side="left", expand=True)
        self.mat_listbox = tk.Listbox(mat_frame, font=('Inter', 10), borderwidth=0, highlightthickness=0)
        self.mat_listbox.pack(fill="x", pady=5)
        mat_btn_frame1 = ttk.Frame(mat_frame)
        mat_btn_frame1.pack(fill="x", pady=(5, 0))
        ttk.Button(mat_btn_frame1, text="추가", command=self._add_material).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(mat_btn_frame1, text="수정", command=self._edit_material).pack(side="left", expand=True, fill="x")
        mat_btn_frame2 = ttk.Frame(mat_frame)
        mat_btn_frame2.pack(fill="x", pady=(5, 0))
        ttk.Button(mat_btn_frame2, text="삭제", command=self._delete_material).pack(side="left", expand=True, fill="x")

        self.member_frame = ttk.LabelFrame(left_pane, text="길드원 관리 (0명)", padding="10")
        self.member_frame.pack(fill="both", expand=True)
        search_entry = ttk.Entry(self.member_frame, textvariable=self.member_search_var)
        search_entry.pack(fill="x", pady=(0, 5))
        search_entry.bind("<KeyRelease>", self._filter_member_list)
        self.member_listbox = tk.Listbox(self.member_frame, selectmode="extended", font=('Inter', 10), borderwidth=0, highlightthickness=0)
        self.member_listbox.pack(fill="both", expand=True, pady=5)
        member_btn_frame = ttk.Frame(self.member_frame)
        member_btn_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(member_btn_frame, text="추가", command=self._add_member).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(member_btn_frame, text="수정", command=self._edit_member).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(member_btn_frame, text="삭제", command=self._delete_member).pack(side="left", expand=True, fill="x")

        right_pane = ttk.Frame(paned_window, padding=10)
        paned_window.add(right_pane, weight=4)
        view_filter_frame = ttk.Frame(right_pane)
        view_filter_frame.pack(fill="x", pady=(0, 10))
        
        radio_button_frame = ttk.Frame(view_filter_frame)
        radio_button_frame.pack(side="left")
        ttk.Radiobutton(radio_button_frame, text="총 재료", variable=self.view_category_var, value="all", command=self._update_display_panes).pack(side="left", padx=5)
        for key, text in CATEGORIES.items():
            ttk.Radiobutton(radio_button_frame, text=text, variable=self.view_category_var, value=key, command=self._update_display_panes).pack(side="left", padx=5)
        
        button_frame_right = ttk.Frame(view_filter_frame)
        button_frame_right.pack(side="right")
        ttk.Button(button_frame_right, text="납품 로그 보기", command=self._show_logs).pack(side="left", padx=(0, 5))
        ttk.Button(button_frame_right, text="납품 랭킹 보기", command=self._show_ranking).pack(side="left")

        self.progress_frame = ttk.LabelFrame(right_pane, text="재료별 진행 상황", padding="10")
        self.progress_frame.pack(fill="x", pady=(0, 10))
        contribution_frame = ttk.LabelFrame(right_pane, text="개인별 기여도 현황", padding="10")
        contribution_frame.pack(fill="both", expand=True)
        
        main_search_frame = ttk.Frame(contribution_frame)
        main_search_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(main_search_frame, text="길드원 검색:").pack(side="left")
        main_search_entry = ttk.Entry(main_search_frame, textvariable=self.main_table_search_var)
        main_search_entry.pack(side="left", fill="x", expand=True, padx=5)
        main_search_entry.bind("<KeyRelease>", lambda e: self._populate_treeview())

        self.tree = ttk.Treeview(contribution_frame, show="headings", style='Treeview')
        vsb = ttk.Scrollbar(contribution_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(contribution_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.bind("<Double-1>", self._edit_cell)

    def _update_ui(self):
        self._update_timestamp_display()
        self._filter_member_list()
        self._update_material_listbox()
        self._update_display_panes()

    def _update_timestamp_display(self):
        ts_data = self.data.get("last_updated", {})
        mat_ts = ts_data.get("materials")
        mem_ts = ts_data.get("members")
        self.materials_updated_label.config(text=f"재료/기여도: {mat_ts}" if mat_ts else "재료/기여도 수정 기록 없음")
        self.members_updated_label.config(text=f"길드원: {mem_ts}" if mem_ts else "길드원 수정 기록 없음")

    def _update_material_listbox(self):
        self.mat_listbox.delete(0, tk.END)
        category = self.manage_category_var.get()
        materials_in_cat = self.data["materials"].get(category, [])
        for mat in materials_in_cat:
            self.mat_listbox.insert(tk.END, f"{mat['name']}: {mat['total']:,}개")
        self.mat_listbox.config(height=len(materials_in_cat) if materials_in_cat else 3)

    def _update_display_panes(self):
        view_cat = self.view_category_var.get()
        self.current_display_materials = []
        if view_cat == "all":
            for cat_key, cat_name in CATEGORIES.items():
                for mat in self.data["materials"].get(cat_key, []):
                    self.current_display_materials.append((mat, cat_key))
        else:
            cat_name = CATEGORIES.get(view_cat)
            for mat in self.data["materials"].get(view_cat, []):
                self.current_display_materials.append((mat, view_cat))
        
        for widget in self.progress_frame.winfo_children(): widget.destroy()
        
        all_contributions = {}
        for cat_key, materials in self.data["materials"].items():
            for mat in materials:
                composite_key = f"{cat_key}:{mat['name']}"
                all_contributions[composite_key] = sum(mem["contributions"].get(composite_key, 0) for mem in self.data["members"])

        cols = 4
        for i, (mat, cat_key) in enumerate(self.current_display_materials):
            row, col = divmod(i, cols)
            p_frame = ttk.Frame(self.progress_frame)
            p_frame.grid(row=row, column=col, padx=5, pady=5, sticky='ew')
            self.progress_frame.grid_columnconfigure(col, weight=1)
            total_needed = mat['total']
            composite_key = f"{cat_key}:{mat['name']}"
            total_submitted = all_contributions.get(composite_key, 0)
            percentage = (total_submitted / total_needed * 100) if total_needed > 0 else 0
            display_text = f"{mat['name']} ({percentage:.1f}%)"
            ttk.Label(p_frame, text=display_text).pack(anchor='w')
            ttk.Progressbar(p_frame, orient='horizontal', length=100, mode='determinate', value=percentage).pack(fill='x', pady=(2, 0))
            ttk.Label(p_frame, text=f"{total_submitted:,} / {total_needed:,}", font=('Inter', 8)).pack(anchor='e')
        self._populate_treeview(all_contributions)

    def _populate_treeview(self, all_contributions=None):
        if all_contributions is None:
            all_contributions = {}
            for cat_key, materials in self.data["materials"].items():
                for mat in materials:
                    composite_key = f"{cat_key}:{mat['name']}"
                    all_contributions[composite_key] = sum(mem["contributions"].get(composite_key, 0) for mem in self.data["members"])

        for i in self.tree.get_children(): self.tree.delete(i)
        
        use_unique_names = self.view_category_var.get() == 'all'
        
        display_columns = ["길드원"]
        for mat, cat_key in self.current_display_materials:
            cat_name = CATEGORIES[cat_key]
            short_cat = cat_name.replace(" 재료", "")
            col_name = f"({short_cat}) {mat['name']}" if use_unique_names else mat['name']
            display_columns.append(col_name)

        self.tree["columns"] = display_columns
        
        self.tree.heading("길드원", text="길드원", anchor="center", command=lambda: self._sort_by_column("길드원"))
        self.tree.column("길드원", width=120, anchor="w", stretch=False)

        for i, (mat, cat_key) in enumerate(self.current_display_materials):
            col_name = display_columns[i + 1]
            composite_key = f"{cat_key}:{mat['name']}"
            self.tree.heading(col_name, text=col_name, anchor="center", command=lambda k=composite_key: self._sort_by_column(k))
            self.tree.column(col_name, anchor="center", width=100, stretch=True)

        members_data = self.data["members"]
        
        search_term = self.main_table_search_var.get().lower()
        if search_term:
            members_data = [m for m in members_data if search_term in m["name"].lower()]

        if self.sort_column and self.sort_column != "길드원":
            members_data = sorted(members_data, key=lambda m: m["contributions"].get(self.sort_column, 0), reverse=self.sort_reverse)
        elif self.sort_column == "길드원":
             members_data = sorted(members_data, key=lambda m: m["name"], reverse=self.sort_reverse)
        
        for i, member in enumerate(members_data):
            if not member or not member.get("name") or not str(member.get("name")).strip(): continue
            values = [member["name"]]
            for mat, cat_key in self.current_display_materials:
                composite_key = f"{cat_key}:{mat['name']}"
                values.append(f"{member['contributions'].get(composite_key, 0):,}")
            self.tree.insert("", "end", values=values, tags=('evenrow' if i % 2 == 0 else 'oddrow',))
        
        if self.data["members"] and not search_term: # 검색 중일 때는 총계 숨김
            total_values = ["총계"]
            for mat, cat_key in self.current_display_materials:
                composite_key = f"{cat_key}:{mat['name']}"
                total_values.append(f"{all_contributions.get(composite_key, 0):,}")
            self.tree.insert("", "end", values=total_values, tags=('total_row',))

    def _sort_by_column(self, col_identifier):
        if self.sort_column == col_identifier: self.sort_reverse = not self.sort_reverse
        else: self.sort_column, self.sort_reverse = col_identifier, False
        self._populate_treeview()

    def _add_material(self):
        category = self.manage_category_var.get()
        dialog = AddMaterialDialog(self.root, "재료 추가", CATEGORIES[category])
        if not dialog.result: return
        name, total = dialog.result['name'], dialog.result['total']
        if any(m['name'] == name for m in self.data['materials'][category]):
            messagebox.showwarning("중복 오류", "해당 카테고리에 이미 존재하는 재료입니다.")
            return
        self.data["materials"][category].append({"name": name, "total": total})
        composite_key = f"{category}:{name}"
        for member in self.data["members"]:
            if composite_key not in member["contributions"]: member["contributions"][composite_key] = 0
        self._update_ui()
        self._save_data('materials')

    def _edit_material(self):
        category = self.manage_category_var.get()
        selected_index = self.mat_listbox.curselection()
        if not selected_index:
            messagebox.showwarning("선택 오류", "수정할 재료를 선택하세요.")
            return
        original_material = self.data["materials"][category][selected_index[0]]
        old_name = original_material['name']
        new_name = simpledialog.askstring("이름 수정", "새 재료 이름을 입력하세요:", initialvalue=old_name)
        if not new_name: return
        if new_name != old_name and any(m['name'] == new_name for m in self.data['materials'][category]):
            messagebox.showwarning("중복 오류", "해당 카테고리에 이미 존재하는 재료 이름입니다.")
            return
        new_total = simpledialog.askinteger("수량 수정", f"'{new_name}'의 총 필요 수량을 입력하세요:", initialvalue=original_material['total'], minvalue=0)
        if new_total is not None:
            original_material['name'], original_material['total'] = new_name, new_total
            if old_name != new_name:
                old_key = f"{category}:{old_name}"
                new_key = f"{category}:{new_name}"
                for member in self.data["members"]:
                    if old_key in member["contributions"]:
                        member["contributions"][new_key] = member["contributions"].pop(old_key)
            self._update_ui()
            self._save_data('materials')

    def _delete_material(self):
        category = self.manage_category_var.get()
        selected_index = self.mat_listbox.curselection()
        if not selected_index:
            messagebox.showwarning("선택 오류", "삭제할 재료를 선택하세요.")
            return
        mat_name = self.data["materials"][category][selected_index[0]]["name"]
        if messagebox.askyesno("삭제 확인", f"'{mat_name}' 재료를 정말 삭제하시겠습니까?"):
            del self.data["materials"][category][selected_index[0]]
            composite_key = f"{category}:{mat_name}"
            for member in self.data["members"]:
                if composite_key in member["contributions"]: del member["contributions"][composite_key]
            self._update_ui()
            self._save_data('materials')

    def _filter_member_list(self, event=None):
        search_term = self.member_search_var.get().lower()
        self.member_listbox.delete(0, tk.END)
        filtered_members = [m for m in self.data["members"] if search_term in m["name"].lower()]
        for member in filtered_members: self.member_listbox.insert(tk.END, member["name"])
        self.member_frame.config(text=f"길드원 관리 ({len(filtered_members)}명 / 총 {len(self.data['members'])}명)")

    def _add_member(self):
        name = simpledialog.askstring("길드원 추가", "추가할 길드원 이름을 입력하세요:")
        if name and name not in [m["name"] for m in self.data["members"]]:
            new_contributions = {}
            for cat_key, materials in self.data['materials'].items():
                for mat in materials:
                    new_contributions[f"{cat_key}:{mat['name']}"] = 0
            new_member = {"name": name, "contributions": new_contributions}
            self.data["members"].append(new_member)
            self._update_ui()
            self._save_data('members')
        elif name:
            messagebox.showwarning("중복 오류", "이미 존재하는 길드원 이름입니다.")

    def _edit_member(self):
        selected_indices = self.member_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("선택 오류", "수정할 길드원을 선택하세요.")
            return
        if len(selected_indices) > 1:
            messagebox.showwarning("선택 오류", "한 번에 한 명의 길드원만 수정할 수 있습니다.")
            return

        old_name = self.member_listbox.get(selected_indices[0])
        new_name = simpledialog.askstring("길드원 이름 수정", "새로운 이름을 입력하세요:", initialvalue=old_name)

        if not new_name or not new_name.strip():
            return

        new_name = new_name.strip()

        if new_name != old_name and any(m["name"] == new_name for m in self.data["members"]):
            messagebox.showwarning("중복 오류", "이미 존재하는 길드원 이름입니다.")
            return

        for member in self.data["members"]:
            if member["name"] == old_name:
                member["name"] = new_name
                break
        
        self._update_ui()
        self._save_data('members')

    def _delete_member(self):
        selected_indices = self.member_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("선택 오류", "삭제할 길드원을 선택하세요.")
            return
        members_to_delete = [self.member_listbox.get(i) for i in selected_indices]
        if messagebox.askyesno("삭제 확인", f"선택한 {len(members_to_delete)}명의 길드원을 정말 삭제하시겠습니까?"):
            self.data["members"] = [m for m in self.data["members"] if m["name"] not in members_to_delete]
            self._update_ui()
            self._save_data('members')

    def _edit_cell(self, event):
        if not self.tree.focus(): return
        selected_iid = self.tree.focus()
        if 'total_row' in self.tree.item(selected_iid, 'tags'): return

        column_id = self.tree.identify_column(event.x)
        column_index = int(column_id.replace('#', '')) - 1
        if column_index == 0: return

        member_name = self.tree.item(selected_iid, 'values')[0]
        material_info, cat_key = self.current_display_materials[column_index - 1]
        composite_key = f"{cat_key}:{material_info['name']}"
        display_name = self.tree.heading(column_id, "text")

        current_value = self.data['members'][next(i for i, m in enumerate(self.data['members']) if m['name'] == member_name)]['contributions'].get(composite_key, 0)
        
        dialog = EditContributionDialog(self.root, "수량 수정", member_name, display_name, current_value)
        new_value = dialog.result

        if new_value is not None:
            # --- ★★★ 기능 개선: 로그 기록 로직 추가 ★★★ ---
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "member": member_name,
                "material_key": composite_key,
                "material_display": display_name,
                "change": new_value - current_value,
                "old_value": current_value,
                "new_value": new_value
            }
            self.data["logs"].append(log_entry)
            # 로그가 너무 많아지면 오래된 로그부터 삭제
            if len(self.data["logs"]) > LOG_LIMIT:
                self.data["logs"] = self.data["logs"][-LOG_LIMIT:]

            for member in self.data["members"]:
                if member["name"] == member_name:
                    member["contributions"][composite_key] = new_value
                    break
            self._update_display_panes()
            self._save_data('materials')

    def _show_ranking(self):
        view_cat_key = self.view_category_var.get()
        
        materials_for_ranking = []
        if view_cat_key == "all":
            category_name = "총 재료"
            for cat_key, materials in self.data['materials'].items():
                for mat in materials:
                    materials_for_ranking.append((mat, cat_key))
        else:
            category_name = CATEGORIES.get(view_cat_key)
            for mat in self.data['materials'].get(view_cat_key, []):
                materials_for_ranking.append((mat, view_cat_key))

        if not materials_for_ranking:
            messagebox.showinfo("정보", f"'{category_name}'에 해당하는 재료가 없습니다.")
            return

        ranking_data = []
        for member in self.data['members']:
            total_contribution = sum(member['contributions'].get(f"{cat_key}:{mat['name']}", 0) for mat, cat_key in materials_for_ranking)
            
            ranking_data.append({
                "name": member['name'],
                "total": total_contribution,
                "contributions": member['contributions']
            })

        ranking_data.sort(key=lambda x: x['total'], reverse=True)

        RankingDialog(self.root, "납품 랭킹", category_name, ranking_data, materials_for_ranking)

    # --- ★★★ 새로운 기능: 로그 보기 메서드 ★★★ ---
    def _show_logs(self):
        logs = self.data.get("logs", [])
        if not logs:
            messagebox.showinfo("정보", "표시할 납품 로그가 없습니다.")
            return
        LogDialog(self.root, logs)

if __name__ == "__main__":
    root = tk.Tk()
    app = GuildContributionTracker(root)
    root.mainloop()
