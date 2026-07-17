"""主窗口 / 控制器（UI 层入口）。

液态苹果风：
- 浅色外观（appearance_mode=light），根窗口静态渐变背景（仅 resize 时重绘一次，零持续动画）
- 顶部：磨砂顶栏（Logo 圆点 + 标题 + 版本 + 状态胶囊）
- 主体：三栏（连接 / 文件 / 预览）磨砂玻璃面板
- 所有阻塞操作仍走 WorkerPool 后台线程，主线程只做 UI 与调度

注：本程序刻意不使用任何持续 after() 动画，因为那些每帧重绘会拖慢窗口
拖动与缩放。后台线程架构保留，它是「界面不卡顿」的真正保障，与动画无关。
"""

import ctypes
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageFilter

from scangate.config import ConfigManager, ConnectionConfig, APP_NAME, VERSION
from scangate.core.worker import WorkerPool, Cancelled
from scangate.services.connection import connect, disconnect
from scangate.services.files import list_files, upload, download, delete
from scangate.services.preview import make_preview
from scangate.ui.panels import ConnectionPanel, FilePanel, PreviewPanel
from scangate.ui.overlay import ProgressOverlay
from scangate.ui.dialogs import AboutDialog, popup, confirm
from scangate.ui.theme import (
    FONT, TEXT, TEXT_DIM, TEXT_FAINT, GLASS, GLASS_ALT, GLASS_BORDER, GLASS_HI,
    GLASS_TINT, GLASS_ALPHA, ACCENT, ACCENT_SOFT, SUCCESS, WARNING, ERROR,
    BG_TOP, BG_BOT, RADIUS,
)
from scangate.ui.fx import (
    lerp_color, round_window, _hex_to_rgb, make_glass_image, make_shadow_image,
    make_background, WindowsCaptionButton,
)


class ScanGateApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # 无边框（去掉系统标题栏与边缘），窗口控制按钮改由主界面内部提供
        self.overrideredirect(True)
        self.title(f"{APP_NAME} · 打印机扫描共享工具")
        self.geometry("1180x700")
        self.minsize(920, 520)
        # 窗口状态（供自定义 最小化/最大化/关闭 使用）
        self._is_max = False
        self._normal_geo = None
        self._normal_w = 1180
        self._normal_h = 700
        self._drag_x = None
        self._drag_y = None
        self._no_drag_widgets = []
        self._rz_side = None  # 边缘缩放状态
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=BG_BOT)

        self.cfg_mgr = ConfigManager()
        self.servers = self.cfg_mgr.load()  # 新版返回 ServerProfile 列表
        # 从当前生效的服务器档派生出 ConnectionConfig 供 UI 使用
        self.config = ConnectionConfig.from_profile(self.cfg_mgr.active())
        self.connected = False
        self._current_items: list[dict] = []

        self.workers = WorkerPool(self)

        self._build_bg()
        self._build_toolbar()
        self._build_content()
        self._build_resize_handles()
        self.overlay = ProgressOverlay(self.content_frame)

        # 注册毛玻璃刷新（顶栏 + 三栏）
        self._glass_refresh = [
            self._refresh_toolbar,
            self.conn_panel.refresh_glass,
            self.file_panel.refresh_glass,
            self.preview_panel.refresh_glass,
        ]

        self.bind("<Configure>", self._on_configure)
        self._draw_bg()

        # 初始绘制（窗口映射后尺寸才稳定）
        self.after(80, lambda: (self._draw_bg(), self._refresh_glass_all()))

        # 无边框窗口在系统级加圆角（Win11 DWM）；延迟到窗口建好后再调用
        self.after(60, lambda: round_window(self.winfo_id()))
        # 无边框窗口默认没有任务栏按钮，补上 WS_EX_APPWINDOW 以便最小化后可从任务栏还原
        self.after(80, self._ensure_taskbar)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 背景（模糊渐变，仅 resize 重绘） ----------------
    def _build_bg(self):
        # 用标签承载模糊渐变图像（支持透明，使毛玻璃面板可透出背景）
        self._bg_label = ctk.CTkLabel(self, text="", fg_color="transparent")
        self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_img = None
        self._bg_w = self._bg_h = -1
        self._cfg_pending = False
        self._glass_refresh = []

    def _draw_bg(self):
        # 生成多段竖向渐变 + 顶部光源高光，再整体高斯模糊 → 朦胧底图，烘托毛玻璃质感
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 2 or h < 2:
                return
            grad = make_background(w, h)
            self._bg_img = ctk.CTkImage(grad, grad, (w, h))
            self._bg_label.configure(image=self._bg_img)
        except Exception:
            pass

    def _on_configure(self, _e):
        # 防抖：连续 resize 事件合并为每 ~40ms 一次刷新，避免逐帧重绘拖慢拖动
        if self._cfg_pending:
            return
        self._cfg_pending = True
        self.after(40, self._do_configure)

    def _do_configure(self):
        self._cfg_pending = False
        try:
            w, h = self.winfo_width(), self.winfo_height()
            if (w, h) != (self._bg_w, self._bg_h):
                self._bg_w, self._bg_h = w, h
                self._draw_bg()
                self._refresh_glass_all()
        except Exception:
            pass

    def _refresh_glass_all(self):
        # 顶栏 + 三栏面板统一刷新磨砂表面（尺寸变化时才真正重绘）
        for cb in getattr(self, "_glass_refresh", []):
            try:
                cb()
            except Exception:
                pass

    # ---------------- 布局 ----------------
    def _build_toolbar(self):
        # 顶栏：透明外壳 + 磨砂表面（resize 时重绘），Windows 风格布局
        bar = ctk.CTkFrame(self, height=52, corner_radius=0, fg_color="transparent")
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        self._bar = bar
        self._bar_surf = ctk.CTkLabel(bar, text="", fg_color="transparent")
        self._bar_surf.place(x=0, y=0, relwidth=1, relheight=1)
        self._bar_surf_img = None

        # 左侧：标题 + 版本
        self._title_label = ctk.CTkLabel(bar, text=APP_NAME, font=FONT["title"],
                                         text_color=TEXT)
        self._title_label.pack(side="left", padx=(18, 0), pady=0)
        self._ver_label = ctk.CTkLabel(bar, text=f"v{VERSION}", font=FONT["mono_sm"],
                                       text_color=TEXT_FAINT)
        self._ver_label.pack(side="left", padx=(8, 0))

        # 右侧：状态胶囊（在窗口控件左侧）
        self.status_pill = ctk.CTkFrame(bar, fg_color=GLASS_ALT, corner_radius=18,
                                       border_color=GLASS_BORDER, border_width=1)
        self.status_pill.pack(side="right", padx=(0, 4), pady=0)
        self.status_dot = ctk.CTkFrame(self.status_pill, width=10, height=10,
                                      corner_radius=5, fg_color=SUCCESS)
        self.status_dot.pack(side="left", padx=(14, 7))
        self.status_label = ctk.CTkLabel(self.status_pill, text="就绪", font=FONT["body"],
                                        text_color=TEXT)
        self.status_label.pack(side="left", padx=(0, 15))

        # 右侧最外：Windows 风格窗口控件（最小化 / 最大化 / 关闭）
        self.win_btns = ctk.CTkFrame(bar, fg_color="transparent")
        self.win_btns.pack(side="right", padx=(0, 2), pady=0)
        WindowsCaptionButton(self.win_btns, "—", self._minimize, "min").pack(side="left")
        self._max_btn = WindowsCaptionButton(self.win_btns, "▢", self._toggle_max, "max")
        self._max_btn.pack(side="left")
        WindowsCaptionButton(self.win_btns, "✕", self._close, "close").pack(side="left")
        for w in self.win_btns.winfo_children():
            self._no_drag_widgets.append(w)

        # 拖拽移动（点击标题栏空白处拖动；避开窗口控制按钮与状态胶囊）
        for w in (bar, self._title_label, self._ver_label):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
        bar.bind("<Double-Button-1>", self._bar_double)

    def _bar_double(self, e):
        if e.widget in self._no_drag_widgets or e.widget is self.status_pill:
            return
        self._toggle_max()

    def _refresh_toolbar(self) -> None:
        # 重绘顶栏磨砂表面（随窗口宽度变化）
        try:
            w, h = self._bar.winfo_width(), self._bar.winfo_height()
            if w < 2 or h < 2:
                return
            if self._bar_surf_img is None or self._bar_surf_img.size != (w, h):
                pil = make_glass_image(
                    w, h, radius=0, alpha=0.72, tint=GLASS_TINT,
                    border=GLASS_BORDER, border_width=0, highlight=GLASS_HI,
                    highlight_alpha=80,
                )
                self._bar_surf_img = ctk.CTkImage(pil, pil, (w, h))
            self._bar_surf.configure(image=self._bar_surf_img)
        except Exception:
            try:
                self._bar.configure(fg_color=GLASS)
            except Exception:
                pass

    # ---------------- 窗口控制（替代系统标题栏） ----------------
    def _start_drag(self, e):
        # 点在控制按钮 / 状态胶囊上不触发拖动
        if e.widget in self._no_drag_widgets or e.widget is self.win_btns \
                or e.widget is self.status_pill:
            return
        self._drag_x = None
        self._drag_y = None
        if self._is_max:
            # 从最大化状态拖拽：先恢复为正常尺寸并跟随鼠标
            nx = e.x_root - self._normal_w // 2
            ny = e.y_root - 22
            self.geometry(f"{self._normal_w}x{self._normal_h}+{nx}+{ny}")
            self._is_max = False
            self._max_btn.configure(text="▢")
            self._drag_x = e.x_root - nx
            self._drag_y = e.y_root - ny
        else:
            self._drag_x = e.x_root - self.winfo_x()
            self._drag_y = e.y_root - self.winfo_y()

    def _do_drag(self, e):
        if self._drag_x is None:
            return
        self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    @staticmethod
    def _workarea():
        """返回主显示器工作区 (x, y, w, h)，自动避开任务栏；失败回退整屏。"""
        try:
            SPI_GETWORKAREA = 0x30

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_int), ("top", ctypes.c_int),
                            ("right", ctypes.c_int), ("bottom", ctypes.c_int)]

            r = RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
            return (r.left, r.top, r.right - r.left, r.bottom - r.top)
        except Exception:
            return (0, 0, 1920, 1080)

    def _ensure_taskbar(self) -> None:
        """为无边框窗口补上任务栏入口（WS_EX_APPWINDOW）。"""
        try:
            hwnd = self.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x40000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_APPWINDOW)
        except Exception:
            pass

    def _minimize(self):
        # 无边框窗口无法直接 iconify（Tk 限制），改用 Win32 API 最小化到任务栏
        try:
            hwnd = self.winfo_id()
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        except Exception:
            try:
                self.withdraw()
            except Exception:
                pass

    def _toggle_max(self, _e=None):
        if self._is_max:
            if self._normal_geo:
                self.geometry(self._normal_geo)
            self._is_max = False
            self._max_btn.configure(text="▢")
        else:
            self._normal_geo = self.geometry()
            try:
                wh = self._normal_geo.split("+")[0].split("x")
                self._normal_w = int(wh[0])
                self._normal_h = int(wh[1])
            except Exception:
                pass
            x, y, w, h = self._workarea()
            self.geometry(f"{w}x{h}+{x}+{y}")
            self._is_max = True
            self._max_btn.configure(text="▣")

    def _close(self):
        self._on_close()

    def _build_content(self):
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=12, pady=(8, 12))
        # 三栏最小宽度之和(230+290+300=820) + 列间距(36) + 内容框边距(24) = 880，
        # 必须 ≤ 窗口最小宽度(920)，否则预览栏右缘会被窗口裁掉（“下一页”按钮看不见）。
        self.content_frame.grid_columnconfigure(0, weight=0, minsize=230)
        self.content_frame.grid_columnconfigure(1, weight=2, minsize=290)
        self.content_frame.grid_columnconfigure(2, weight=1, minsize=300)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self.conn_panel = ConnectionPanel(
            self.content_frame, self.config,
            self._on_connect, self._on_disconnect, self._on_about,
        )
        self.conn_panel.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        self.file_panel = FilePanel(
            self.content_frame,
            {
                "refresh": self._on_refresh,
                "upload": self._on_upload,
                "download": self._on_download,
                "delete": self._on_delete,
                "select": self._on_select,
            },
        )
        self.file_panel.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

        self.preview_panel = PreviewPanel(self.content_frame, on_page=self._on_preview_nav)
        self.preview_panel.grid(row=0, column=2, sticky="nsew", padx=6, pady=6)

    # ---------------- 边缘自由缩放（无边框窗口必需） ----------------
    def _build_resize_handles(self):
        """在窗口 8 个边缘/角落放置透明拖拽热区，模拟系统边缘缩放。"""
        specs = {
            "n":  dict(relx=0.0, rely=0.0, relwidth=1.0, height=6,  anchor="nw", cursor="sb_v_double_arrow", side="n"),
            "s":  dict(relx=0.0, rely=1.0, relwidth=1.0, height=6,  anchor="sw", cursor="sb_v_double_arrow", side="s"),
            "w":  dict(relx=0.0, rely=0.0, relheight=1.0, width=6,  anchor="nw", cursor="sb_h_double_arrow", side="w"),
            "e":  dict(relx=1.0, rely=0.0, relheight=1.0, width=6,  anchor="ne", cursor="sb_h_double_arrow", side="e"),
            "ne": dict(relx=1.0, rely=0.0, width=12, height=12, anchor="ne", cursor="size_ne_sw", side="ne"),
            "nw": dict(relx=0.0, rely=0.0, width=12, height=12, anchor="nw", cursor="size_nw_se", side="nw"),
            "se": dict(relx=1.0, rely=1.0, width=12, height=12, anchor="se", cursor="size_nw_se", side="se"),
            "sw": dict(relx=0.0, rely=1.0, width=12, height=12, anchor="sw", cursor="size_ne_sw", side="sw"),
        }
        self._handles = {}
        for name, sp in specs.items():
            # 角落热区需要固定宽高 —— 必须传进构造器（CTkFrame.place 不接受 width/height）
            wh = {}
            if "width" in sp:
                wh["width"] = sp["width"]
            if "height" in sp:
                wh["height"] = sp["height"]
            h = ctk.CTkFrame(self, fg_color="transparent", cursor=sp["cursor"], **wh)
            place_kw = dict(relx=sp["relx"], rely=sp["rely"], anchor=sp["anchor"])
            if "relwidth" in sp:
                place_kw["relwidth"] = sp["relwidth"]
            if "relheight" in sp:
                place_kw["relheight"] = sp["relheight"]
            h.place(**place_kw)
            h.bind("<Enter>", lambda e, c=sp["cursor"]: self.configure(cursor=c))
            h.bind("<Leave>", lambda e: self.configure(cursor=""))
            h.bind("<Button-1>", lambda e, side=sp["side"]: self._resize_start(e, side))
            h.bind("<B1-Motion>", self._resize_move)
            self._no_drag_widgets.append(h)
            self._handles[name] = h

    def _resize_start(self, e, side: str) -> None:
        if self._is_max:  # 最大化时不缩放
            return
        self._rz_side = side
        self._rz_x0 = e.x_root
        self._rz_y0 = e.y_root
        parts = self.geometry().replace("x", "+").split("+")
        self._rz_w0 = int(parts[0])
        self._rz_h0 = int(parts[1])
        self._rz_x0w = int(parts[2])
        self._rz_y0w = int(parts[3])

    def _resize_move(self, e) -> None:
        if self._rz_side is None:
            return
        dx = e.x_root - self._rz_x0
        dy = e.y_root - self._rz_y0
        side = self._rz_side
        minw, minh = 920, 520
        x, y = self._rz_x0w, self._rz_y0w
        w, h = self._rz_w0, self._rz_h0
        if "e" in side:
            w = max(minw, self._rz_w0 + dx)
        if "s" in side:
            h = max(minh, self._rz_h0 + dy)
        if "w" in side:
            nw = max(minw, self._rz_w0 - dx)
            x = self._rz_x0w + (self._rz_w0 - nw)
            w = nw
        if "n" in side:
            nh = max(minh, self._rz_h0 - dy)
            y = self._rz_y0w + (self._rz_h0 - nh)
            h = nh
        self.geometry(f"{w}x{h}+{x}+{y}")
        if not self._is_max:
            self._normal_geo = f"{w}x{h}+{x}+{y}"
            self._normal_w, self._normal_h = w, h

    # ---------------- 状态 ----------------
    def _set_status(self, text: str, color=None):
        self.status_label.configure(text=text)
        if color is not None:
            self.status_dot.configure(fg_color=color)

    # ---------------- 连接 ----------------
    def _on_connect(self):
        self.config = self.conn_panel.get_config()
        # 把连接面板的改动写回当前生效的服务器配置并持久化
        prof = self.cfg_mgr.active()
        prof.host = self.config.host
        prof.share = self.config.share
        prof.subfolder = self.config.subfolder
        prof.username = self.config.username
        prof.password = self.config.password
        self.cfg_mgr.save()
        self.overlay.show("正在连接共享…")
        self._set_status("连接中…", WARNING)

        def done(_ok):
            self.overlay.hide()
            self.connected = True
            self.conn_panel.set_status("已连接", connected=True)
            self._set_status("已连接", SUCCESS)
            self._on_refresh()

        def err(e):
            self.overlay.hide()
            self.connected = False
            self.conn_panel.set_status("连接失败")
            self._set_status("连接失败", ERROR)
            popup(self, "连接失败", str(e))

        self.workers.submit(connect, args=(self.config,), on_done=done, on_error=err, task_id="connect")

    def _on_disconnect(self):
        if not self.connected:
            return
        self.overlay.show("正在断开…")

        def done(_):
            self.overlay.hide()
            self.connected = False
            self.conn_panel.set_status("未连接")
            self._set_status("已断开", SUCCESS)

        self.workers.submit(disconnect, args=(self.config,), on_done=done, on_error=done, task_id="disconnect")

    # ---------------- 文件列表 ----------------
    def _on_refresh(self):
        if not self.connected:
            popup(self, "未连接", "请先连接共享")
            return
        self.overlay.show("正在读取文件列表…")

        def done(items):
            self.overlay.hide()
            self._current_items = items
            self.file_panel.set_items(items)
            self._set_status(f"共 {len(items)} 项", SUCCESS)

        def err(e):
            self.overlay.hide()
            self._set_status("读取失败", ERROR)
            popup(self, "读取失败", str(e))

        self.workers.submit(list_files, args=(self.config.root_path,), on_done=done, on_error=err, task_id="list")

    # ---------------- 预览 ----------------
    def _on_select(self, item: dict):
        self._preview_item = item
        self._preview_page = 0
        self._request_preview()

    def _request_preview(self) -> None:
        item = self._preview_item
        page = self._preview_page
        self.overlay.show(f"预览 {item['name']}…")

        def done(result):
            self.overlay.hide()
            if not isinstance(result, dict):
                self.preview_panel.show_text("无法生成预览")
                return
            self._preview_page = result.get("page", page)  # 同步真实页码，防止越界累积
            img = result.get("image")
            if img is None:
                self.preview_panel.show_text("无法生成预览")
            else:
                self.preview_panel.show_image(
                    img, item["name"], result.get("page", 0), result.get("total", 1)
                )

        def err(e):
            self.overlay.hide()
            msg = str(e) if "PyMuPDF" in str(e) else "无法预览此文件"
            self.preview_panel.show_text(msg)

        self.workers.submit(make_preview, args=(item["path"],), kwargs={"page": page},
                            on_done=done, on_error=err, task_id="preview")

    def _on_preview_nav(self, delta: int) -> None:
        if getattr(self, "_preview_item", None) is None:
            return
        new_page = self._preview_page + delta
        if new_page < 0:
            return
        self._preview_page = new_page
        self._request_preview()

    # ---------------- 上传 ----------------
    def _on_upload(self):
        if not self.connected:
            popup(self, "未连接", "请先连接共享")
            return
        paths = filedialog.askopenfilenames(title="选择要上传的文件")
        if not paths:
            return
        self.overlay.show("上传中…", cancel_cb=lambda: self.workers.cancel("upload"))
        dest_dir = self.config.root_path
        results = {"ok": 0, "fail": 0}

        def worker_run(progress, cancel):
            for p in paths:
                if cancel.is_cancelled():
                    raise Cancelled()
                try:
                    upload(progress, cancel, p, dest_dir)
                    results["ok"] += 1
                except Cancelled:
                    raise
                except Exception:
                    results["fail"] += 1
            return results

        def done(_r):
            self.overlay.hide()
            self._set_status(f"上传完成：成功 {results['ok']} / 失败 {results['fail']}", SUCCESS)
            self._on_refresh()

        def err(e):
            self.overlay.hide()
            popup(self, "上传失败", str(e))

        def prog(p, m):
            self.overlay.set_progress(p, m)

        self.workers.submit(worker_run, on_done=done, on_error=err, on_progress=prog, task_id="upload")

    # ---------------- 下载 ----------------
    def _on_download(self):
        item = self.file_panel.selected()
        if not item:
            popup(self, "提示", "请先选择要下载的文件")
            return
        if item["is_dir"]:
            popup(self, "提示", "暂不支持下载文件夹")
            return
        dest = filedialog.asksaveasfilename(
            title="保存为", initialfile=item["name"],
            defaultextension=__import__("os").path.splitext(item["name"])[1],
        )
        if not dest:
            return
        self.overlay.show(f"下载 {item['name']}…", cancel_cb=lambda: self.workers.cancel("download"))

        def done(_):
            self.overlay.hide()
            self._set_status("下载完成", SUCCESS)

        def err(e):
            self.overlay.hide()
            popup(self, "下载失败", str(e))

        def prog(p, m):
            self.overlay.set_progress(p, m)

        self.workers.submit(download, args=(item["path"], dest), on_done=done,
                            on_error=err, on_progress=prog, task_id="download")

    # ---------------- 删除 ----------------
    def _on_delete(self):
        item = self.file_panel.selected()
        if not item:
            popup(self, "提示", "请先选择要删除的文件")
            return
        if not confirm(self, f"确定删除 {item['name']}？此操作不可恢复。"):
            return
        self.overlay.show(f"删除 {item['name']}…")

        def done(_):
            self.overlay.hide()
            self._on_refresh()

        def err(e):
            self.overlay.hide()
            popup(self, "删除失败", str(e))

        self.workers.submit(delete, args=(item["path"],), on_done=done, on_error=err, task_id="delete")

    # ---------------- 其它 ----------------
    def _on_about(self):
        AboutDialog(self)

    def _on_close(self):
        self.destroy()
