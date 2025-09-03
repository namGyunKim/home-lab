import tkinter as tk
from tkinter import messagebox
import calendar
from datetime import datetime, timedelta
import json
import os
import math
d
try:a
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *f
except ImportError:
    messagebox.showerror("라이브러리 오류", "'ttkbootstrap' 라이브러리가 설치되지 않았습니다.\n터미널에서 'pip install ttkbootstrap'를 실행해주세요.")
    exit()

calendar.setfirstweekday(calendar.SUNDAY)

class AbyssScheduler:
    # 클래스 상수 정의
    INTERVAL = timedelta(hours=36, minutes=15)
    DATA_FILE = "abyss_schedule_data.json"
    WINDOW_TITLE = "어비스 구멍 일정"
    DAY_COLOR = "warning"  # 낮 시간 이벤트 색상 (ttkbootstrap 테마 색상)
    NIGHT_COLOR = "info"   # 밤 시간 이벤트 색상 (ttkbootstrap 테마 색상)
    TODAY_COLOR = "primary" # 오늘 날짜를 위한 색상 (ttkbootstrap 테마 색상)
    CLOSEST_EVENT_COLOR = "success" # 가장 가까운 일정 강조 색상 (초록색)

    # 패치노트 내용 정의
    PATCH_NOTES = """
    [Patch Note]

    v1.0 (2025-08-28)
    - 어비스 구멍 일정 관리 프로그램이 새롭게 시작되었습니다.
    - 현대적인 UI (superhero 테마)가 적용되었습니다.
    - 현재 시각 이후의 가장 가까운 일정이 초록색으로 강조됩니다.
    - 낮/밤 시간대에 따라 일정의 배경색이 변경됩니다.
    - 현재 주를 포함하여 총 3주 분량의 달력만 표시됩니다.
    - 시작 날짜와 시간을 설정하고 저장하여 일정을 관리할 수 있습니다.
    """

    def __init__(self, root):
        self.root = root
        self.root.title(self.WINDOW_TITLE)
        self.root.geometry("800x600")  # 창 크기 조정
        self.root.resizable(False, False)

        self.view_date = datetime.now()
        self.start_time = self._load_start_time()

        self._create_widgets()
        self._update_calendar()

    def _load_start_time(self):
        """데이터 파일에서 시작 시간을 로드합니다."""
        if not os.path.exists(self.DATA_FILE):
            print("데이터 파일이 존재하지 않습니다. 기본값으로 시작합니다.")
            return None

        try:
            with open(self.DATA_FILE, 'r') as f:
                data = json.load(f)
                return datetime.fromisoformat(data['start_time'])
        except (IOError, json.JSONDecodeError, KeyError) as e:
            messagebox.showerror("오류", f"데이터 로딩 중 오류가 발생했습니다: {e}\n기존 파일을 삭제하고 다시 시도해주세요.")
            return None

    def _save_start_time(self):
        """입력된 시작 시간을 저장하고 캘린더를 갱신합니다."""
        date_str = self.date_entry.entry.get()
        time_str = f"{self.hour_spinbox.get()}:{self.minute_spinbox.get()}"

        try:
            new_start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            self.start_time = new_start_time

            with open(self.DATA_FILE, 'w') as f:
                json.dump({'start_time': self.start_time.isoformat()}, f, indent=4)

            messagebox.showinfo("성공", "시작 시간이 성공적으로 저장되었습니다.")
            self._update_calendar()

        except ValueError:
            messagebox.showerror("입력 오류", "유효한 날짜와 시간을 선택해주세요.")

    def _update_calendar(self):
        """캘린더의 날짜와 이벤트를 갱신합니다."""
        # 기존 날짜 위젯 모두 삭제
        for widget in self.dates_frame.winfo_children():
            widget.destroy()

        self.month_label.config(text=self.view_date.strftime("%Y년 %m월"))

        # 캘린더에 표시될 날짜 범위 계산
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday() + 1)
        grid_start_date = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        grid_end_date = grid_start_date + timedelta(days=20) # 3주 분량 (21일)

        # 달력 범위 내의 모든 이벤트 계산
        events = self._calculate_events(grid_start_date, grid_end_date)

        # 모든 이벤트 중에서 현재 시각 이후의 가장 가까운 이벤트를 찾습니다.
        closest_event = None
        min_diff = timedelta.max
        all_events = [item for sublist in events.values() for item in sublist]
        for event_dt in all_events:
            if event_dt >= today:
                time_diff = event_dt - today
                if time_diff < min_diff:
                    min_diff = time_diff
                    closest_event = event_dt

        # 다음 일정 라벨 업데이트
        if closest_event:
            # 한글 요일 리스트
            weekdays_kr = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            weekday_kr = weekdays_kr[closest_event.weekday()]

            self.next_event_label.config(
            text=f"다음 일정: {closest_event.strftime('%Y년 %m월 %d일')} ({weekday_kr}) {closest_event.strftime('%H시 %M분')}",
            bootstyle="success",
            font=("Arial", 16, "bold")
)
        else:
            self.next_event_label.config(text="다음 일정이 없습니다.", bootstyle="danger")

        # 캘린더 그리기 (3주 x 7일)
        current_date = grid_start_date
        for r in range(3):
            self.dates_frame.grid_rowconfigure(r, weight=1)
            for c in range(7):
                self.dates_frame.grid_columnconfigure(c, weight=1)

                self._draw_day_frame(current_date, c, r, events, today, closest_event)

                current_date += timedelta(days=1)

    def _calculate_events(self, start_date, end_date):
        """지정된 날짜 범위 내의 모든 이벤트 시간을 계산합니다."""
        events = {}
        if not self.start_time:
            return events

        current_event = self.start_time

        while current_event.date() <= end_date.date():
            if current_event < start_date:
                current_event += self.INTERVAL
                continue

            event_date = current_event.date()
            if event_date not in events:
                events[event_date] = []
            events[event_date].append(current_event) # datetime 객체 자체를 저장하여 시간 정보를 유지

            current_event += self.INTERVAL

        return events

    def _draw_day_frame(self, current_date, column, row, events, now, closest_event):
        """단일 날짜 프레임을 그리고 이벤트를 표시합니다."""
        frame_bg_color = "secondary"
        label_fg_color = "white"

        is_current_month = (current_date.month == self.view_date.month)

        if not is_current_month:
            label_fg_color = "gray"
            frame_bg_color = "#353839"
        elif column == 0:
            label_fg_color = "tomato"
        elif column == 6:
            label_fg_color = "skyblue"

        if current_date.date() == now.date():
            frame_bg_color = "primary"
            label_fg_color = "white"

        day_frame = ttk.Frame(self.dates_frame, style="Secondary.TFrame", borderwidth=1, relief="solid")
        day_frame.grid(row=row, column=column, sticky="nsew", padx=2, pady=2)

        day_label = ttk.Label(day_frame, text=str(current_date.day), anchor="nw", padding=5, foreground=label_fg_color, font=("Arial", 12, "bold")) # 폰트 크기 조정
        day_label.pack(fill=tk.X)

        if current_date.date() in events:
            for event_dt in events[current_date.date()]:
                event_hour = event_dt.hour

                if event_dt == closest_event:
                    event_bg = self.CLOSEST_EVENT_COLOR
                # 낮 (오전 6시 ~ 오후 6시)
                elif 6 <= event_hour < 18:
                    event_bg = self.DAY_COLOR
                # 밤 (그 외)
                else:
                    event_bg = self.NIGHT_COLOR

                event_label = ttk.Label(day_frame, text=event_dt.strftime("%H:%M"), style=f"{event_bg}.TLabel", font=("Arial", 10, "bold")) # 폰트 크기 조정
                event_label.pack(pady=4, padx=4, fill=tk.X) # 패딩 조정

    def _create_widgets(self):
        """UI 위젯을 생성하고 배치합니다."""
        # 탭 위젯 생성
        notebook = ttk.Notebook(self.root)
        notebook.pack(expand=True, fill="both", padx=15, pady=15) # 전체 패딩 조정

        # 캘린더 탭 프레임
        calendar_tab = ttk.Frame(notebook)
        notebook.add(calendar_tab, text="달력")

        # 패치 노트 탭 프레임
        patch_note_tab = ttk.Frame(notebook)
        notebook.add(patch_note_tab, text="패치 노트")

        # 상단 컨트롤 프레임 (캘린더 탭에 속함)
        control_frame = ttk.Frame(calendar_tab)
        control_frame.pack(fill=tk.X, pady=10) # 패딩 조정

        ttk.Label(control_frame, text="시작 날짜:").pack(side=tk.LEFT, padx=(0, 5))
        self.date_entry = ttk.DateEntry(control_frame, bootstyle="primary")
        self.date_entry.pack(side=tk.LEFT, padx=5)

        ttk.Label(control_frame, text="시작 시간:").pack(side=tk.LEFT, padx=(10, 5))

        self.hour_spinbox = ttk.Spinbox(control_frame, from_=0, to=23, wrap=True, width=3, bootstyle="secondary")
        self.hour_spinbox.pack(side=tk.LEFT, padx=1)

        ttk.Label(control_frame, text=":").pack(side=tk.LEFT)

        self.minute_spinbox = ttk.Spinbox(control_frame, from_=0, to=59, wrap=True, width=3, bootstyle="secondary")
        self.minute_spinbox.pack(side=tk.LEFT, padx=1)

        save_button = ttk.Button(control_frame, text="저장 및 갱신", command=self._save_start_time, bootstyle="success")
        save_button.pack(side=tk.LEFT, padx=10)

        if self.start_time:
            self.date_entry.entry.delete(0, tk.END)
            self.date_entry.entry.insert(0, self.start_time.strftime("%Y-%m-%d"))
            self.hour_spinbox.set(self.start_time.strftime("%H"))
            self.minute_spinbox.set(self.start_time.strftime("%M"))
        else:
            self.hour_spinbox.set("18")
            self.minute_spinbox.set("00")

        # 캘린더 프레임 (캘린더 탭에 속함)
        calendar_frame = ttk.Frame(calendar_tab)
        calendar_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=0)  # pady를 0으로 조정하여 간격 제거

        nav_frame = ttk.Frame(calendar_frame)
        nav_frame.pack(fill=tk.X, pady=2)

        self.month_label = ttk.Label(nav_frame, text="", font=("Arial", 16, "bold")) # 폰트 크기 조정
        self.month_label.pack(side=tk.TOP, expand=True)
        self.next_event_label = ttk.Label(nav_frame, text="", font=("Arial", 20, "bold"))
        self.next_event_label.pack(side=tk.TOP, pady=5)

        days_frame = ttk.Frame(calendar_frame)
        days_frame.pack(fill=tk.X, pady=0) # pady를 0으로 조정하여 간격 제거
        days = ["일", "월", "화", "수", "목", "금", "토"]

        # 요일 라벨만 표시
        for i, day in enumerate(days):
            day_color = "danger" if day == "일" else "info" if day == "토" else "secondary"
            lbl = ttk.Label(days_frame, text=day, width=10, anchor="center", bootstyle=day_color, font=("Arial", 12, "bold")) # 폰트 크기 조정
            lbl.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
            days_frame.grid_columnconfigure(i, weight=1)

        self.dates_frame = ttk.Frame(calendar_tab)
        self.dates_frame.pack(expand=True, fill=tk.BOTH)

        # 패치 노트 위젯 (패치 노트 탭에 속함)
        patch_text = tk.Text(patch_note_tab, wrap="word", relief="flat", padx=10, pady=10)
        patch_text.insert(tk.END, self.PATCH_NOTES)
        patch_text.config(state="disabled") # 읽기 전용으로 설정

        # 스크롤바 추가
        scrollbar = ttk.Scrollbar(patch_note_tab, command=patch_text.yview)
        patch_text.config(yscrollcommand=scrollbar.set)

        patch_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


    def _change_month(self, delta):
        """월을 안전하게 변경합니다."""
        first_day_of_view_month = self.view_date.replace(day=1)

        if delta > 0:
            target_day = first_day_of_view_month + timedelta(days=32)
        else:
            target_day = first_day_of_view_month - timedelta(days=1)

        self.view_date = target_day.replace(day=1)
        self._update_calendar()

if __name__ == "__main__":
    # 루트 윈도우 생성 시 부트스트랩 테마를 적용합니다.
    root = ttk.Window(themename="superhero")
    app = AbyssScheduler(root)
    root.mainloop()
