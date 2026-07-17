"""UI 面板组件（纯展示 + 回调，不含业务逻辑）。

液态苹果风：磨砂玻璃面板（顶部高光 + 浅灰描边 + 大圆角）+ 浅色文件列表。
所有控件统一调用 ui.theme / ui.fx，保证风格一致。
每个面板通过回调（callbacks）与上层控制器通信，保持单向依赖。
"""

import datetime

import customtkinter as ctk
from tkinter import ttk

from scangate.config import ConnectionConfig
from scangate.ui.theme import (
    FONT, TEXT, TEXT_DIM, GLASS_ALT, GLASS_BORDER, GLASS_HI, GLASS_TINT, GLASS_ALPHA,
    ACCENT, ACCENT_SOFT, SUCCESS, DANGER, button, RADIUS, SP,
)
from scangate.ui.fx import safe_configure, make_glass_image, make_shadow_image


# ---------------- 浅色 Treeview 样式 ----------------
_TREE_STYLE_READY = False


def _ensure_tree_style() -> None:
    global _TREE_STYLE_READY
    if _TREE_STYLE_READY:
        return
    try:
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(
            "ScanGate.Treeview",
            background=GLASS_TINT,
            foreground=TEXT,
            fieldbackground=GLASS_TINT,
            borderwidth=0,
            relief="flat",
            rowheight=40,
            font=FONT["body"],
        )
        s.map(
            "ScanGate.Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#0a3a7a")],
            relief=[("selected", "flat")],
        )
        s.configure(
            "ScanGate.Treeview.Heading",
            background=GLASS_ALT,
            foreground=TEXT_DIM,
            borderwidth=0,
            relief="flat",
            font=FONT["small"],
        )
        s.configure(
            "ScanGate.Vertical.TScrollbar",
            background=GLASS_ALT,
            troughcolor=GLASS_TINT,
            borderwidth=0,
            relief="flat",
        )
        s.map("ScanGate.Vertical.TScrollbar", background=[("active", ACCENT)])
        _TREE_STYLE_READY = True
    except Exception:
        pass


class _SectionHeader(ctk.CTkFrame):
    def __init__(self, master, title: str, accent: str = ACCENT):
        super().__init__(master, fg_color="transparent")
        dot = ctk.CTkFrame(self, width=9, height=9, corner_radius=5, fg_color=accent)
        dot.pack(side="left", padx=(SP["md"], SP["sm"]), pady=(SP["md"], SP["sm"]))
        ctk.CTkLabel(self, text=title, font=FONT["section"], text_color=TEXT).pack(
            side="left", pady=(SP["sm"], SP["xs"])
        )


class _GlassPanel(ctk.CTkFrame):
    """毛玻璃面板：半透明磨砂表面（白色微透 + 中性描边 + 顶部高光）
    + 柔和投影（悬浮抬升感）。表面与投影均为图像，resize 时按需重绘。"""

    def __init__(self, master, accent: str = ACCENT):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self._accent = accent
        self._gw = self._gh = 0
        self._surf_img = None
        self._shadow_img = None
        # 投影（最底层）
        self._shadow = ctk.CTkLabel(self, text="", fg_color="transparent")
        self._shadow.place(relx=0.5, rely=0.52, anchor="center",
                           relwidth=1.05, relheight=1.06)
        # 磨砂表面
        self._surf = ctk.CTkLabel(self, text="", fg_color="transparent")
        self._surf.place(relx=0.5, rely=0.5, anchor="center",
                         relwidth=1.0, relheight=1.0)
        # 内容层
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.place(relx=0.5, rely=0.5, anchor="center",
                         relwidth=1.0, relheight=1.0)

    def refresh_glass(self) -> None:
        """按当前像素尺寸重绘磨砂表面与投影（resize 时调用，尺寸不变则跳过）。"""
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2 or (w, h) == (self._gw, self._gh):
            return
        self._gw, self._gh = w, h
        try:
            if self._surf_img is None or self._surf_img.size != (w, h):
                pil = make_glass_image(
                    w, h, radius=RADIUS, alpha=GLASS_ALPHA, tint=GLASS_TINT,
                    border=GLASS_BORDER, border_width=1.5, highlight=GLASS_HI,
                )
                self._surf_img = ctk.CTkImage(pil, pil, (w, h))
            self._surf.configure(image=self._surf_img)
            if self._shadow_img is None or self._shadow_img.size != (w + 20, h + 24):
                sp = make_shadow_image(w, h, radius=RADIUS, blur=22, alpha=0.16, offset=8)
                self._shadow_img = ctk.CTkImage(sp, sp, (sp.width, sp.height))
            self._shadow.configure(image=self._shadow_img)
        except Exception:
            # 兜底：图像生成失败则退化为冷白实底面板（仍可用）
            try:
                self.configure(fg_color=GLASS_TINT)
            except Exception:
                pass


class ConnectionPanel(_GlassPanel):
    def __init__(self, master, config: ConnectionConfig, on_connect, on_disconnect, on_about):
        super().__init__(master, accent=ACCENT)
        _SectionHeader(self._body, "连接设置", ACCENT)

        self._vars = {}
        fields = [
            ("host", "服务器地址"),
            ("share", "共享名"),
            ("subfolder", "子目录"),
            ("username", "用户名"),
            ("password", "密码"),
        ]
        for key, label in fields:
            ctk.CTkLabel(self._body, text=label, anchor="w", font=FONT["body"],
                        text_color=TEXT_DIM).pack(fill="x", padx=SP["md"],
                                                  pady=(SP["md"], 0))
            var = ctk.StringVar(value=getattr(config, key))
            ent = ctk.CTkEntry(self._body, textvariable=var, font=FONT["body"],
                              fg_color=GLASS_ALT, border_color=GLASS_BORDER,
                              text_color=TEXT, corner_radius=12,
                              show="*" if key == "password" else None)
            ent.pack(fill="x", padx=SP["md"], pady=(SP["xs"], SP["sm"]))
            ent.bind("<FocusIn>", lambda e, en=ent: safe_configure(
                en, border_color=ACCENT, border_width=2))
            ent.bind("<FocusOut>", lambda e, en=ent: safe_configure(
                en, border_color=GLASS_BORDER, border_width=1))
            self._vars[key] = var

        self.status = ctk.CTkLabel(self._body, text="未连接", font=FONT["body"],
                                   text_color=TEXT_DIM)
        self.status.pack(pady=SP["md"])

        button(self._body, text="连接共享", command=on_connect, kind="primary",
               width=220).pack(fill="x", padx=SP["md"], pady=(SP["xs"], SP["xs"]))
        button(self._body, text="断开连接", command=on_disconnect, kind="secondary",
               width=220).pack(fill="x", padx=SP["md"], pady=(SP["xs"], SP["xs"]))
        button(self._body, text="关于程序", command=on_about, kind="ghost",
               width=220).pack(fill="x", padx=SP["md"], pady=(SP["xs"], SP["md"]))

    def get_config(self) -> ConnectionConfig:
        return ConnectionConfig(**{k: v.get() for k, v in self._vars.items()})

    def set_status(self, text: str, connected: bool = False) -> None:
        safe_configure(self.status, text=text,
                       text_color=(SUCCESS if connected else DANGER))


class FilePanel(_GlassPanel):
    def __init__(self, master, callbacks: dict):
        super().__init__(master, accent=ACCENT)
        self.cb = callbacks
        self._items: list[dict] = []

        _SectionHeader(self._body, "文件列表", ACCENT)

        top = ctk.CTkFrame(self._body, fg_color="transparent")
        top.pack(fill="x", padx=SP["md"], pady=(SP["xs"], SP["md"]))
        for i, (label, key, kind) in enumerate([
            ("刷新", "refresh", "primary"),
            ("上传", "upload", "primary"),
            ("下载", "download", "primary"),
            ("删除", "delete", "danger"),
        ]):
            top.grid_columnconfigure(i, weight=1)
            # 等宽自适应：按钮随面板宽度均匀铺开，窄面板也不会被裁切
            button(top, text=label, command=self.cb[key], kind=kind).grid(
                row=0, column=i, padx=SP["xs"], sticky="ew"
            )

        list_frame = ctk.CTkFrame(self._body, fg_color=GLASS_TINT, corner_radius=16,
                                  border_color=GLASS_BORDER, border_width=1)
        list_frame.pack(fill="both", expand=True, padx=SP["md"], pady=SP["sm"])

        _ensure_tree_style()
        self.tree = ttk.Treeview(
            list_frame, style="ScanGate.Treeview",
            columns=("name", "size", "mtime"), show="headings", selectmode="browse",
        )
        self.tree.heading("name", text="名称")
        self.tree.heading("size", text="大小")
        self.tree.heading("mtime", text="修改时间")
        self.tree.column("name", width=200)
        self.tree.column("size", width=80)
        self.tree.column("mtime", width=120)
        self.tree.tag_configure("dir", foreground=ACCENT)
        self.tree.tag_configure("file", foreground=TEXT)
        self.tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(list_frame, orient="vertical",
                          style="ScanGate.Vertical.TScrollbar",
                          command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def set_items(self, items: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._items = items
        for it in items:
            size = "" if it["is_dir"] else self._fmt(it["size"])
            mtime = self._fmt_time(it["mtime"])
            self.tree.insert(
                "",
                "end",
                values=(it["name"], size, mtime),
                tags=("dir" if it["is_dir"] else "file"),
            )

    def selected(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        return self._items[idx] if 0 <= idx < len(self._items) else None

    def _on_select(self, _e) -> None:
        item = self.selected()
        if item and not item["is_dir"] and self.cb.get("select"):
            self.cb["select"](item)

    @staticmethod
    def _fmt(n: float) -> str:
        n = float(n)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if n < 1024:
                return f"{n:.0f}{unit}"
            n /= 1024
        return f"{n:.0f}TB"

    @staticmethod
    def _fmt_time(t: float) -> str:
        return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")


class PreviewPanel(_GlassPanel):
    def __init__(self, master, on_page=None):
        super().__init__(master, accent=ACCENT)
        _SectionHeader(self._body, "预览", ACCENT)
        self._on_page = on_page
        self._name = ""
        self._page = 0
        self._total = 1

        self.info = ctk.CTkLabel(self._body, text="选择文件以预览", font=FONT["body"],
                                text_color=TEXT_DIM)
        self.info.pack(side="top", pady=SP["sm"])
        self.img_label = ctk.CTkLabel(self._body, text="")
        self.img_label.pack(side="top", expand=True, fill="both",
                            padx=SP["sm"], pady=(SP["sm"], SP["sm"]))
        self._ctk_img = None

        # 翻页导航条：用 place() 锚定在预览面板底部、随面板宽度自适应缩放。
        # 这样完全不受三栏 grid 列宽溢出影响，任何窗口尺寸下都完整可见。
        self.nav = ctk.CTkFrame(self._body, fg_color="transparent")
        self._prev = button(self.nav, text="‹ 上一页", command=lambda: self._go(-1),
                            kind="secondary")
        self._prev.pack(side="left", fill="x", expand=True, padx=(SP["sm"], SP["xs"]))
        self.page_label = ctk.CTkLabel(self.nav, text="", font=FONT["body"],
                                       text_color=TEXT_DIM, anchor="center")
        self.page_label.pack(side="left", fill="x", expand=True, padx=SP["xs"])
        self._next = button(self.nav, text="下一页 ›", command=lambda: self._go(1),
                            kind="secondary")
        self._next.pack(side="left", fill="x", expand=True, padx=(SP["xs"], SP["sm"]))
        # 先 place 到屏幕外（窗口底部外），默认隐藏
        self.nav.place(relx=0.0, rely=1.0, y=-10, relwidth=1.0, anchor="sw")
        self._nav_visible = False
        self._set_nav(False)

    def _go(self, delta: int) -> None:
        if self._on_page:
            self._on_page(delta)

    def _set_nav(self, visible: bool) -> None:
        if visible == self._nav_visible:
            return
        self._nav_visible = visible
        if visible:
            # 重新放置（之前可能 place_forget 过）
            self.nav.place(relx=0.0, rely=1.0, y=-10, relwidth=1.0, anchor="sw")
            # 给预览图底部预留翻页条空间，避免被遮住
            safe_configure(self.img_label, pady=(6, 46))
        else:
            self.nav.place_forget()
            safe_configure(self.img_label, pady=(6, 6))

    def _refresh_nav(self) -> None:
        multi = self._total > 1
        self._set_nav(multi)
        if multi:
            safe_configure(self.info,
                           text=f"{self._name}  ·  第 {self._page + 1} / {self._total} 页")
            safe_configure(self._prev, state="normal" if self._page > 0 else "disabled")
            safe_configure(self._next,
                           state="normal" if self._page < self._total - 1 else "disabled")
        else:
            safe_configure(self.info, text=self._name)

    def show_image(self, pil_img, name: str, page: int = 0, total: int = 1) -> None:
        self._ctk_img = ctk.CTkImage(
            light_image=pil_img, dark_image=pil_img, size=pil_img.size
        )
        safe_configure(self.img_label, image=self._ctk_img, text="")
        self._name = name
        self._page = page
        self._total = total
        self._refresh_nav()

    def show_text(self, text: str) -> None:
        self._ctk_img = None
        safe_configure(self.img_label, image=None, text=text)
        self._set_nav(False)
        safe_configure(self.info, text="")

    def clear(self) -> None:
        self._ctk_img = None
        safe_configure(self.img_label, image=None, text="")
        self._set_nav(False)
        safe_configure(self.info, text="选择文件以预览")
