import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """내용이 창보다 클 때 스크롤할 수 있는 컨테이너.

    화면 해상도가 낮거나 Windows 디스플레이 배율이 높으면 탭 내용이 창 높이를
    넘어서 아래쪽(재생 설정, 상태바 등)이 잘려 보이지 않는다.
    실제 내용은 `interior`에 배치하고, 필요할 때만 스크롤바를 표시한다.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        background = self._lookup_background()

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                background=background)
        self.vbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)

        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.vbar.grid(row=0, column=1, sticky='ns')
        self.hbar.grid(row=1, column=0, sticky='ew')
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.interior = ttk.Frame(self.canvas)
        self._window_id = self.canvas.create_window((0, 0), window=self.interior, anchor='nw')

        self.interior.bind('<Configure>', self._on_content_changed)
        self.canvas.bind('<Configure>', self._on_content_changed)
        # 마우스가 올라와 있을 때만 휠 스크롤을 받는다. (다른 위젯 스크롤 방해 방지)
        self.canvas.bind('<Enter>', self._bind_wheel)
        self.canvas.bind('<Leave>', self._unbind_wheel)

    def _lookup_background(self):
        try:
            color = ttk.Style().lookup('TFrame', 'background')
            if color:
                return color
        except tk.TclError:
            pass
        return '#e7eef9'

    def _on_content_changed(self, event=None):
        try:
            need_w = self.interior.winfo_reqwidth()
            need_h = self.interior.winfo_reqheight()
            view_w = self.canvas.winfo_width()
            view_h = self.canvas.winfo_height()

            # 창이 내용보다 크면 내용을 창 크기에 맞춰 늘려 기존처럼 꽉 차게 하고,
            # 창이 내용보다 작을 때만 스크롤이 생기도록 한다.
            full_w = max(need_w, view_w)
            full_h = max(need_h, view_h)
            self.canvas.itemconfigure(self._window_id, width=full_w, height=full_h)
            self.canvas.configure(scrollregion=(0, 0, full_w, full_h))

            self._toggle_bar(self.vbar, need_h > view_h + 1, 'grid')
            self._toggle_bar(self.hbar, need_w > view_w + 1, 'grid')
        except tk.TclError:
            pass

    def _toggle_bar(self, bar, should_show, _mode):
        if should_show:
            if not bar.winfo_ismapped():
                bar.grid()
        else:
            if bar.winfo_ismapped():
                bar.grid_remove()

    def _bind_wheel(self, event=None):
        self.canvas.bind_all('<MouseWheel>', self._on_wheel)
        self.canvas.bind_all('<Button-4>', self._on_wheel)
        self.canvas.bind_all('<Button-5>', self._on_wheel)

    def _unbind_wheel(self, event=None):
        self.canvas.unbind_all('<MouseWheel>')
        self.canvas.unbind_all('<Button-4>')
        self.canvas.unbind_all('<Button-5>')

    def _on_wheel(self, event):
        try:
            # 스크롤할 내용이 없으면 무시한다.
            if self.interior.winfo_reqheight() <= self.canvas.winfo_height():
                return
            if getattr(event, 'num', None) == 4:
                delta = -1
            elif getattr(event, 'num', None) == 5:
                delta = 1
            else:
                delta = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(delta, 'units')
        except tk.TclError:
            pass
