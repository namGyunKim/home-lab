import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk


def set_widget_state_recursive(parent, state):
    """컨테이너 하위의 모든 위젯 상태를 일괄 변경합니다.

    직계 자식만 순회하면 Frame 안에 들어 있는 라디오버튼 등이 빠져
    재생 중에도 설정을 바꿀 수 있게 된다.
    Combobox는 활성 상태가 'readonly'여야 임의 입력을 막을 수 있다.
    """
    for child in parent.winfo_children():
        try:
            if child.winfo_class() == "TCombobox":
                child.config(state="readonly" if state == tk.NORMAL else tk.DISABLED)
            else:
                child.config(state=state)
        except tk.TclError:
            # Frame처럼 state 옵션이 없는 위젯은 건너뛰고 하위만 처리한다.
            pass
        set_widget_state_recursive(child, state)


def heading_width(text, padding=36, minimum=80):
    """Treeview 헤딩 문구가 잘리지 않는 컬럼 폭을 계산합니다.

    컬럼 폭을 픽셀로 고정하면 디스플레이 배율이 높거나 문구가 길 때
    헤딩 글자가 잘려 보인다. 실제 폰트로 폭을 재서 결정한다.
    """
    try:
        font_spec = ttk.Style().lookup("Treeview.Heading", "font")
        if not font_spec:
            font_spec = ("Malgun Gothic", 11, "bold")
        measured = tkFont.Font(font=font_spec).measure(text)
    except tk.TclError:
        measured = len(text) * 12
    return max(minimum, measured + padding)
