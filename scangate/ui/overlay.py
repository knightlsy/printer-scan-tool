"""非阻塞进度遮罩（轻量 · 液态苹果风）。

- 磨砂玻璃卡片（近白 + 浅灰描边 + 大圆角）
- 进度使用 customtkinter 原生 CTkProgressBar（indeterminate / determinate 两种模式），
  不手写 canvas 逐帧绘制，避免任何持续重绘开销
- 取消按钮（危险红）
"""

import customtkinter as ctk

from scangate.ui.theme import (
    FONT, TEXT, TEXT_DIM, GLASS, GLASS_ALT, GLASS_BORDER, ACCENT, DANGER, DANGER_HI, RADIUS,
)
from scangate.ui.fx import AppleButton, safe_configure


class ProgressOverlay:
    def __init__(self, parent):
        self.parent = parent
        self._visible = False
        self._cancel_cb = None

        self.frame = ctk.CTkFrame(parent, corner_radius=RADIUS, fg_color=GLASS,
                                 border_color=GLASS_BORDER, border_width=1)
        self.label = ctk.CTkLabel(self.frame, text="处理中…", font=FONT["body"],
                                  text_color=TEXT)
        self.bar = ctk.CTkProgressBar(self.frame, width=360, height=10,
                                     mode="indeterminate",
                                     progress_color=ACCENT, border_color=GLASS_BORDER,
                                     fg_color=GLASS_ALT)
        self.cancel_btn = AppleButton(self.frame, text="取消", kind="danger",
                                      width=100, command=self._on_cancel)

        self.label.pack(pady=(18, 12))
        self.bar.pack(fill="x", padx=26, pady=2)
        self.cancel_btn.pack(pady=(14, 18))
        self.frame.place(relx=0.5, rely=0.5, anchor="center")
        self.frame.place_forget()

    def show(self, text: str = "处理中…", cancel_cb=None) -> None:
        self._cancel_cb = cancel_cb
        safe_configure(self.label, text=text)
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self.frame.place(relx=0.5, rely=0.5, anchor="center")
        self.frame.lift()
        self._visible = True

    def set_progress(self, pct: float, msg: str = "") -> None:
        if pct is not None:
            self.bar.stop()
            self.bar.configure(mode="determinate")
            self.bar.set(max(0.0, min(1.0, pct / 100.0)))
        if msg:
            safe_configure(self.label, text=msg)

    def _on_cancel(self) -> None:
        if self._cancel_cb:
            self._cancel_cb()

    def hide(self) -> None:
        self._visible = False
        try:
            self.bar.stop()
        except Exception:
            pass
        self.frame.place_forget()
