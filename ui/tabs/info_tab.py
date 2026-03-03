import tkinter as tk
from tkinter import ttk, scrolledtext
import tkinter.font as tkFont
import webbrowser

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
