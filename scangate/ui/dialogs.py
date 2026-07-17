"""对话框与提示（关于 / 相关链接 / 信息弹窗 / 确认）。

液态苹果风（磨砂玻璃、大圆角、浅色）：
- AboutDialog：关于窗口，作者「刘思元」为可点击蓝色按钮
- LinksDialog：仅显示「公司内」「公司外」两个药丸大按钮，点击用浏览器打开，
  不展示任何 URL 文本
- 所有弹窗均为静态样式（无持续动画）
"""

import webbrowser

import customtkinter as ctk
import tkinter.messagebox as mb

from scangate.config import APP_NAME, VERSION, AUTHOR, COPYRIGHT, LINK_INTERNAL, LINK_EXTERNAL
from scangate.ui.theme import (
    FONT, TEXT_DIM, GLASS, GLASS_ALT, GLASS_BORDER, ACCENT, INDIGO, TEXT, RADIUS, SP,
)
from scangate.ui.fx import AppleButton, round_window, make_glass_image, WindowsCaptionButton


def _center_geo(parent, w: int, h: int) -> str:
    parent.update_idletasks()
    px = max(0, parent.winfo_rootx() + (parent.winfo_width() - w) // 2)
    py = max(0, parent.winfo_rooty() + (parent.winfo_height() - h) // 2)
    return f"{w}x{h}+{px}+{py}"


class _GlassDialog(ctk.CTkToplevel):
    """磨砂玻璃弹窗基类（无系统边框，自带标题条与关闭按钮，可拖动）。"""

    def __init__(self, parent, title: str, w: int, h: int):
        super().__init__(parent)
        self.title(title)
        self.geometry(_center_geo(parent, w, h))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.overrideredirect(True)  # 与主窗口一致：无系统边框
        self.configure(fg_color=GLASS)
        # 自定义标题条（可拖动 + 关闭按钮）
        header = ctk.CTkFrame(self, fg_color="transparent", height=40, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text=title, font=FONT["body"], text_color=TEXT
                     ).pack(side="left", padx=SP["md"])
        WindowsCaptionButton(header, "✕", self.destroy, "close",
                             width=36, height=30).pack(side="right", padx=SP["xs"])
        header.bind("<Button-1>", self._drag_start)
        header.bind("<B1-Motion>", self._drag_move)
        # 主体玻璃面板（子类继续往 self._body 里 pack，无需改动）
        self._body = ctk.CTkFrame(self, fg_color="transparent", border_color=GLASS_BORDER,
                                  border_width=1, corner_radius=RADIUS)
        self._body_surf = ctk.CTkLabel(self._body, text="", fg_color="transparent")
        self._body_surf.place(x=0, y=0, relwidth=1, relheight=1)
        self._body_surf_img = None
        self._body.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self._dx = None
        self._dy = None
        self.after(60, lambda: round_window(self.winfo_id()))
        self.after(90, self._refresh_body)

    def _refresh_body(self) -> None:
        try:
            w, h = self._body.winfo_width(), self._body.winfo_height()
            if w < 2 or h < 2:
                return
            if self._body_surf_img is None or self._body_surf_img.size != (w, h):
                pil = make_glass_image(w, h, radius=RADIUS, alpha=0.92,
                                       tint=GLASS_TINT, border=GLASS_BORDER,
                                       border_width=1.5, highlight=GLASS_HI)
                self._body_surf_img = ctk.CTkImage(pil, pil, (w, h))
            self._body_surf.configure(image=self._body_surf_img)
        except Exception:
            try:
                self._body.configure(fg_color=GLASS)
            except Exception:
                pass

    def _drag_start(self, e):
        self._dx = e.x_root - self.winfo_x()
        self._dy = e.y_root - self.winfo_y()

    def _drag_move(self, e):
        if self._dx is None:
            return
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")


class AboutDialog(_GlassDialog):
    def __init__(self, parent):
        super().__init__(parent, f"关于 {APP_NAME}", 480, 380)

        ctk.CTkLabel(self._body, text=APP_NAME, font=FONT["display"],
                    text_color=TEXT).pack(pady=(SP["xl"], SP["xs"]))
        ctk.CTkLabel(self._body, text=f"打印机扫描共享管理工具  v{VERSION}",
                    font=FONT["body"], text_color=TEXT_DIM).pack()

        ctk.CTkFrame(self._body, height=1, fg_color=GLASS_BORDER).pack(
            fill="x", padx=SP["xl"], pady=SP["md"])

        row = ctk.CTkFrame(self._body, fg_color="transparent")
        row.pack()
        ctk.CTkLabel(row, text="开发者", font=FONT["body"], text_color=TEXT).pack(side="left")
        AppleButton(row, text=AUTHOR, kind="ghost", width=130,
                   command=self._open_links).pack(side="left", padx=SP["sm"])

        ctk.CTkLabel(self._body, text=COPYRIGHT, font=FONT["body"],
                    text_color=TEXT).pack(pady=(SP["md"], SP["xs"]))
        ctk.CTkLabel(self._body, text="All Rights Reserved.", font=FONT["small"],
                    text_color=TEXT_DIM).pack()

        AppleButton(self._body, text="关闭", kind="secondary", width=130,
                   command=self.destroy).pack(pady=(SP["lg"], 0))

    def _open_links(self):
        LinksDialog(self)


class LinksDialog(_GlassDialog):
    """仅显示「公司内」「公司外」两个药丸按钮，点击用浏览器打开对应链接。"""

    def __init__(self, parent):
        super().__init__(parent, "相关链接", 460, 320)

        ctk.CTkLabel(self._body, text="选择加入方式", font=FONT["section"],
                    text_color=TEXT).pack(pady=(SP["xl"], SP["xs"]))
        ctk.CTkLabel(self._body, text="点击以下按钮，将在浏览器中打开邀请",
                    font=FONT["small"], text_color=TEXT_DIM).pack(pady=(0, SP["md"]))

        self._link_btn("公司内", LINK_INTERNAL, ACCENT)
        self._link_btn("公司外", LINK_EXTERNAL, INDIGO)

        AppleButton(self._body, text="关闭", kind="secondary", width=130,
                   command=self.destroy).pack(pady=(SP["md"], SP["sm"]))

    def _link_btn(self, label: str, url: str, accent):
        btn = AppleButton(self._body, text=label, kind="primary",
                         width=280, height=46, command=lambda u=url: webbrowser.open(u))
        # 公司外用靛蓝区分：覆盖配色
        if accent == INDIGO:
            btn.configure(fg_color=INDIGO, hover_color="#4a48c4", text_color="#ffffff")
        btn.pack(pady=8)


def popup(parent, title: str, msg: str) -> None:
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    dlg.geometry(_center_geo(parent, 440, 190))
    dlg.transient(parent)
    dlg.grab_set()
    dlg.overrideredirect(True)  # 与主窗口一致：无系统边框
    dlg.configure(fg_color=GLASS)
    header = ctk.CTkFrame(dlg, fg_color="transparent", height=40, corner_radius=0)
    header.pack(fill="x", side="top")
    header.pack_propagate(False)
    ctk.CTkLabel(header, text=title, font=FONT["body"], text_color=TEXT
                 ).pack(side="left", padx=SP["md"])
    WindowsCaptionButton(header, "✕", dlg.destroy, "close",
                         width=36, height=30).pack(side="right", padx=SP["xs"])
    dx = [None]
    dy = [None]

    def _start(e):
        dx[0] = e.x_root - dlg.winfo_x()
        dy[0] = e.y_root - dlg.winfo_y()

    def _move(e):
        if dx[0] is None:
            return
        dlg.geometry(f"+{e.x_root - dx[0]}+{e.y_root - dy[0]}")

    header.bind("<Button-1>", _start)
    header.bind("<B1-Motion>", _move)
    dlg.after(60, lambda: round_window(dlg.winfo_id()))
    body = ctk.CTkFrame(dlg, fg_color="transparent", border_color=GLASS_BORDER,
                       border_width=1, corner_radius=RADIUS)
    body_surf = ctk.CTkLabel(body, text="", fg_color="transparent")
    body_surf.place(x=0, y=0, relwidth=1, relheight=1)
    body.pack(fill="both", expand=True, padx=1, pady=(0, 1))

    def _refresh():
        try:
            w, h = body.winfo_width(), body.winfo_height()
            if w < 2 or h < 2:
                return
            pil = make_glass_image(w, h, radius=RADIUS, alpha=0.92,
                                  tint=GLASS_TINT, border=GLASS_BORDER,
                                  border_width=1.5, highlight=GLASS_HI)
            body_surf.configure(image=ctk.CTkImage(pil, pil, (w, h)))
        except Exception:
            try:
                body.configure(fg_color=GLASS)
            except Exception:
                pass

    dlg.after(90, _refresh)
    ctk.CTkLabel(body, text=msg, font=FONT["body"], wraplength=380,
                text_color=TEXT).pack(pady=SP["md"])
    AppleButton(body, text="确定", kind="secondary", width=120,
              command=dlg.destroy).pack(pady=(SP["sm"], SP["md"]))


def confirm(parent, msg: str) -> bool:
    return mb.askyesno("确认", msg)
