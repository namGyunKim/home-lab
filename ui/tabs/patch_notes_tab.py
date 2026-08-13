import tkinter as tk
from tkinter import ttk, scrolledtext

class PatchNotesTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self._create_widgets()

    def _create_widgets(self):
        notes_frame = ttk.LabelFrame(self, text="버전 정보 및 변경 사항", style="Card.TLabelframe")
        notes_frame.pack(fill=tk.BOTH, expand=True)
        notes_text_widget = scrolledtext.ScrolledText(
            notes_frame, wrap=tk.WORD, padx=15, pady=13, bd=0, font=("Malgun Gothic", 12),
            bg="#ffffff", fg="#152a43", insertbackground="#152a43",
            relief=tk.FLAT, highlightthickness=1, highlightbackground="#cad7e9",
            spacing1=3, spacing3=5
        )
        notes_text_widget.pack(fill=tk.BOTH, expand=True)
        notes_text_widget.tag_configure("title", font=("Malgun Gothic", 17, "bold"), spacing3=13, foreground="#13263d")
        notes_text_widget.tag_configure("subtitle", font=("Malgun Gothic", 13, "bold"), spacing1=15, spacing3=7, lmargin1=4, foreground="#1f3858")
        notes_text_widget.tag_configure("item", font=("Malgun Gothic", 12), lmargin1=17, lmargin2=17, spacing1=5, spacing3=3)

        notes_text_widget.insert(tk.END, "푸크로 V4.8 (Stability Update)\n", "title")
        notes_text_widget.insert(tk.END, "주요 개선사항 (V4.8)\n", "subtitle")
        notes_text_widget.insert(tk.END, "• 🖥️ [해상도] 화면이 작거나 배율이 높아도 탭 내용이 잘리지 않도록 스크롤을 지원합니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🔤 [가독성] 목록 제목과 행 높이를 글자 크기에 맞춰 계산해 글자 잘림을 없앴습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🖱️ [다중 모니터] 보조 모니터에서 녹화한 동작이 무시되던 문제를 해결했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🛡️ [안정성] 중지·오류 시 키/마우스가 눌린 채 남는 문제를 방지합니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🔒 [안정성] 매크로가 동시에 실행되지 않도록 조정해 입력 충돌을 막습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🔍 [이미지] 이미지 대기 정확도를 설정할 수 있고, 인식 실패 원인을 로그로 알립니다.\n", "item")

        notes_text_widget.insert(tk.END, "\n이전 변경사항 (V4.7)\n", "subtitle")
        notes_text_widget.insert(tk.END, "• ✨ [UI] 패치노트 탭을 제거하고 핵심 기능 탭 중심으로 정리했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 👀 [가독성] 버튼/텍스트 대비와 폰트 크기를 조정해 시인성을 높였습니다.\n", "item")

        notes_text_widget.insert(tk.END, "\n이전 변경사항 (V4.6)\n", "subtitle")
        notes_text_widget.insert(tk.END, "• 🚀 [성능] 이미지 캐싱 시스템을 도입하여 검색 속도와 효율을 극대화했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 🛡️ [안정성] UI 스레드 처리 로직을 전면 개편하여 '응답 없음' 현상을 방지했습니다.\n", "item")
        notes_text_widget.insert(tk.END, "• 👁️ [편의성] '항상 위에 표시' 옵션 및 메뉴바를 추가했습니다.\n", "item")

        notes_text_widget.insert(tk.END, "\n이전 변경사항 (V4.5)\n", "subtitle")
        notes_text_widget.insert(tk.END, "• 📝 [도움말] 상세 사용 설명서 내장\n", "item")
        notes_text_widget.insert(tk.END, "• ⌨️ [기능] 단축키 처리 로직 개선\n", "item")

        notes_text_widget.config(state=tk.DISABLED)

