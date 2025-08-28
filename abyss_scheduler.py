import tkinter as tk
from tkinter import ttk, messagebox
import calendar
from datetime import datetime, timedelta
import json
import os
import math

try:
    from tkcalendar import DateEntry
except ImportError:
    messagebox.showerror("라이브러리 오류", "'tkcalendar' 라이브러리가 설치되지 않았습니다.\n터미널에서 'pip install tkcalendar'를 실행해주세요.")
    exit()

calendar.setfirstweekday(calendar.SUNDAY)

# --- 상수 정의 ---
INTERVAL = timedelta(hours=36, minutes=15)
DATA_FILE = "abyss_schedule_data.json"
WINDOW_TITLE = "어비스 구멍 일정 (버그 수정)"
HIGHLIGHT_COLOR = "#3498db"
HIGHLIGHT_TEXT_COLOR = "white"

class AbyssScheduler:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("650x550")
        self.root.resizable(False, False)

        self.view_date = datetime.now()
        self.start_time = self._load_start_time()

        self._create_widgets()
        self._update_calendar()

    def _load_start_time(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    return datetime.fromisoformat(data['start_time'])
        except (IOError, json.JSONDecodeError, KeyError) as e:
            messagebox.showerror("오류", f"데이터 로딩 실패: {e}")
        return None

    def _save_start_time(self):
        date_str = self.date_entry.get()
        time_str = self.time_entry.get()

        try:
            new_start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            self.start_time = new_start_time

            with open(DATA_FILE, 'w') as f:
                json.dump({'start_time': self.start_time.isoformat()}, f, indent=4)

            messagebox.showinfo("성공", "시작 시간이 저장되었습니다. 캘린더를 갱신합니다.")
            self._update_calendar()

        except ValueError:
            messagebox.showerror("입력 오류", "시간을 'HH:MM' 형식으로 정확히 입력해주세요.")

    def _update_calendar(self):
        # 1. 기존 날짜 위젯 모두 삭제
        for widget in self.dates_frame.winfo_children():
            widget.destroy()

        # 2. 현재 월 레이블 업데이트
        self.month_label.config(text=self.view_date.strftime("%Y년 %m월"))

        # 3. 달력에 표시될 날짜 범위 계산
        year = self.view_date.year
        month = self.view_date.month
        
        first_day_of_month = datetime(year, month, 1)
        # datetime.weekday()는 월요일=0, 일요일=6
        first_day_weekday = first_day_of_month.weekday() 
        
        # 달력의 시작 날짜(일요일)를 계산
        days_to_subtract = (first_day_weekday + 1) % 7
        grid_start_date = first_day_of_month - timedelta(days=days_to_subtract)
        
        # 달력의 마지막 날짜 계산 (6주)
        grid_end_date = grid_start_date + timedelta(days=41)

        # 4. 달력 범위 내의 모든 이벤트 계산
        events = {}  # Key: datetime.date, Value: ["HH:MM", ...]
        if self.start_time:
            # 시작 시간과 달력 시작 날짜의 차이를 기반으로 첫 이벤트 위치 계산
            time_diff = grid_start_date - self.start_time
            num_intervals = time_diff.total_seconds() / INTERVAL.total_seconds()
            current_event = self.start_time + (math.floor(num_intervals) * INTERVAL)

            # 달력 범위 내의 모든 이벤트를 찾음
            while current_event.date() <= grid_end_date.date():
                # 이벤트가 달력 시작 날짜보다 이전이면 다음 간격으로 넘어감
                if current_event < grid_start_date:
                    current_event += INTERVAL
                    continue
                
                event_date = current_event.date()
                if event_date not in events:
                    events[event_date] = []
                events[event_date].append(current_event.strftime("%H:%M"))
                
                current_event += INTERVAL

        # 5. 캘린더 그리기 (6주 x 7일)
        current_date = grid_start_date
        for r in range(6):
            self.dates_frame.grid_rowconfigure(r, weight=1)
            for c in range(7):
                self.dates_frame.grid_columnconfigure(c, weight=1)
                
                day_frame = tk.Frame(self.dates_frame, borderwidth=1, relief="solid")
                day_frame.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)

                day_label = tk.Label(day_frame, text=str(current_date.day), anchor="nw", padx=3, pady=2)
                day_label.pack(fill=tk.X)
                
                # 현재 월이 아니면 회색, 맞으면 검은색 (일/토는 색상 지정)
                is_current_month = (current_date.month == month)
                day_fg_color = "gray" if not is_current_month else "black"
                if c == 0: day_fg_color = "gray" if not is_current_month else "red"
                elif c == 6: day_fg_color = "gray" if not is_current_month else "blue"
                day_label.config(fg=day_fg_color)

                # 해당 날짜에 이벤트가 있으면 강조 표시
                if current_date.date() in events:
                    day_frame.config(bg=HIGHLIGHT_COLOR)
                    day_label.config(bg=HIGHLIGHT_COLOR, fg=HIGHLIGHT_TEXT_COLOR, font=("Arial", 9, "bold"))
                    event_text = "\n".join(events[current_date.date()])
                    event_label = tk.Label(day_frame, text=event_text, bg=HIGHLIGHT_COLOR, fg=HIGHLIGHT_TEXT_COLOR, font=("Arial", 9, "bold"))
                    event_label.pack(expand=True)
                
                current_date += timedelta(days=1)
    
    def _create_widgets(self):
        # --- 상단 컨트롤 프레임 ---
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X, pady=5)
        ttk.Label(control_frame, text="시작 날짜:").pack(side=tk.LEFT, padx=(0, 5))
        self.date_entry = DateEntry(control_frame, width=12, date_pattern='y-mm-dd', locale='ko_KR')
        self.date_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(control_frame, text="시작 시간 (HH:MM):").pack(side=tk.LEFT, padx=(10, 5))
        self.time_entry = ttk.Entry(control_frame, width=8)
        self.time_entry.pack(side=tk.LEFT, padx=5)
        save_button = ttk.Button(control_frame, text="저장 및 갱신", command=self._save_start_time)
        save_button.pack(side=tk.LEFT, padx=10)
        
        # 저장된 시작 시간이 있으면 불러오고, 없으면 기본값 설정
        if self.start_time:
            self.date_entry.set_date(self.start_time.date())
            self.time_entry.insert(0, self.start_time.strftime("%H:%M"))
        else:
            self.time_entry.insert(0, "18:00")
            
        # --- 캘린더 프레임 ---
        calendar_frame = ttk.Frame(self.root, padding="10")
        calendar_frame.pack(expand=True, fill=tk.BOTH)
        
        # 월 이동 네비게이션 프레임
        nav_frame = ttk.Frame(calendar_frame)
        nav_frame.pack(fill=tk.X, pady=5)
        prev_button = ttk.Button(nav_frame, text="< 이전 달", command=lambda: self._change_month(-1))
        prev_button.pack(side=tk.LEFT)
        self.month_label = ttk.Label(nav_frame, text="", font=("Arial", 14, "bold"))
        self.month_label.pack(side=tk.LEFT, expand=True)
        next_button = ttk.Button(nav_frame, text="다음 달 >", command=lambda: self._change_month(1))
        next_button.pack(side=tk.RIGHT)
        
        # 요일 표시 프레임
        days_frame = ttk.Frame(calendar_frame)
        days_frame.pack(fill=tk.X)
        days = ["일", "월", "화", "수", "목", "금", "토"]
        for i, day in enumerate(days):
            day_color = "red" if day == "일" else "blue" if day == "토" else "black"
            lbl = ttk.Label(days_frame, text=day, width=10, anchor="center", foreground=day_color, font=("Arial", 10, "bold"))
            lbl.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)
            days_frame.grid_columnconfigure(i, weight=1)
            
        # 날짜가 표시될 메인 프레임
        self.dates_frame = ttk.Frame(calendar_frame)
        self.dates_frame.pack(expand=True, fill=tk.BOTH)

    def _change_month(self, delta):
        """
        월을 안전하게 변경하는 수정된 함수입니다.
        직접 월/연도를 계산하는 대신 timedelta를 사용하여 날짜 계산 오류를 방지합니다.
        """
        # 1. 현재 보고 있는 달의 1일로 기준을 잡습니다.
        first_day_of_view_month = self.view_date.replace(day=1)
        
        # 2. 기준일로부터 날짜를 더하거나 빼서 목표 월로 이동합니다.
        if delta > 0:
            # 다음 달로 가기 위해 32일을 더하면 안전하게 다음 달로 넘어갑니다.
            target_day = first_day_of_view_month + timedelta(days=32)
        else:
            # 이전 달로 가기 위해 하루를 빼면 안전하게 이전 달로 넘어갑니다.
            target_day = first_day_of_view_month - timedelta(days=1)
            
        # 3. 목표 월에 도착했으므로, 다시 1일로 설정하여 최종 기준 날짜를 정합니다.
        self.view_date = target_day.replace(day=1)
        
        # 4. 변경된 날짜를 기준으로 캘린더를 다시 그립니다.
        self._update_calendar()

if __name__ == "__main__":
    root = tk.Tk()
    app = AbyssScheduler(root)
    root.mainloop()
