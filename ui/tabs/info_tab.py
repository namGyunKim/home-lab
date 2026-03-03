import tkinter as tk
from tkinter import ttk, scrolledtext
import tkinter.font as tkFont
import webbrowser

class InfoTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self._create_widgets()

    def _create_widgets(self):
        # 개발자 링크
        link_container = ttk.Frame(self)
        link_container.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        source_text_label = ttk.Label(link_container, text="개발자 블로그 (출처): ")
        source_text_label.pack(side=tk.LEFT, padx=(0, 2))
        url = "https://blog.naver.com/skarbs01/223983468359"
        link_label = ttk.Label(link_container, text=url, style="Link.TLabel", cursor="hand2")
        link_label.pack(side=tk.LEFT)
        f = tkFont.Font(link_label, link_label.cget("font"))
        f.configure(underline=True)
        link_label.configure(font=f)
        link_label.bind("<Button-1>", lambda e: webbrowser.open_new(url))

        # 도움말 내용
        info_frame = ttk.LabelFrame(self, text="푸크로 (Pucro) 매크로 - 사용 설명서", style="Card.TLabelframe")
        info_frame.pack(fill=tk.BOTH, expand=True)
        help_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, padx=15, pady=13, bd=0, font=("Malgun Gothic", 12),
            bg="#ffffff", fg="#152a43", insertbackground="#152a43",
            relief=tk.FLAT, highlightthickness=1, highlightbackground="#cad7e9",
            spacing1=3, spacing3=5
        )
        help_text.pack(fill=tk.BOTH, expand=True)

        # 스타일 태그 설정
        help_text.tag_configure("h1", font=("Malgun Gothic", 18, "bold"), spacing1=3, spacing3=15, foreground="#13263d")
        help_text.tag_configure("h2", font=("Malgun Gothic", 14, "bold"), spacing1=17, spacing3=7, foreground="#1f3858")
        help_text.tag_configure("h3", font=("Malgun Gothic", 12, "bold"), spacing1=13, foreground="#3f556f")
        help_text.tag_configure("bold", font=("Malgun Gothic", 12, "bold"))
        help_text.tag_configure("item", lmargin1=24, lmargin2=24, spacing1=5, spacing3=3)
        help_text.tag_configure("code", font=("Consolas", 11), background="#edf3ff", foreground="#1f3858")

        # 매뉴얼 내용 삽입
        help_text.insert(tk.END, "📘 푸크로(Pucro) 매크로 사용 설명서\n", "h1")
        help_text.insert(tk.END, "푸크로는 반복적인 컴퓨터 작업을 자동화해주는 프로그램입니다.\n마우스/키보드 동작을 녹화하거나, 화면의 이미지를 인식하여 클릭하게 할 수 있습니다.\n\n")

        help_text.insert(tk.END, "1. 탭별 기능 소개\n", "h2")
        # ... (기존 내용 생략, 필요시 추가) ...
        help_text.insert(tk.END, "사용 설명서 내용은 블로그를 참고해주세요.\n", "item")

        help_text.config(state=tk.DISABLED)
