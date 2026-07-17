#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打印机扫描工具 - 未来感界面版
赛博朋克风格，霓虹特效，全动画反馈
"""

import os
import sys
import ctypes  # 单实例互斥锁（Windows 互斥体，防重复启动）
import subprocess
import threading
import traceback

# 隐藏子进程控制台窗口（Windows 下 net/ping 是控制台程序，否则 --windowed 打包后仍会闪一下黑框）
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
import time
import math
import random
import shutil
import socket
import json
from datetime import datetime
from collections import deque

import customtkinter as ctk
from tkinter import filedialog, messagebox, Menu
from PIL import Image

# 可预览的文件类型
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}
# 注：原代码用 TkinterDnD.Tk() 作根窗口，但 customtkinter 6.x 的 CTkButton 命令在
# 普通 tk.Tk 根下不会触发点击 → “按钮全失效”。现改用 customtkinter.CTk 作根（官方推荐、
# 点击最稳），拖拽上传功能由“↑ 上传文件”按钮替代，后续可用 TkinterDnD.require() 兼容方案再加回。

# ── 全局配色方案 ──
CYBER_COLORS = {
    "bg_primary": "#0a0a14",
    "bg_secondary": "#0d0d20",
    "bg_card": "#111128",
    "bg_input": "#0f0f24",
    "neon_cyan": "#00e5ff",
    "neon_magenta": "#ff00e5",
    "neon_green": "#00ff88",
    "neon_yellow": "#ffcc00",
    "neon_red": "#ff3333",
    "neon_blue": "#448aff",
    "text_primary": "#e0e0f0",
    "text_secondary": "#8888aa",
    "text_dim": "#555577",
    "border_glow": "#1a1a40",
    "accent_gradient_start": "#00b4d8",
    "accent_gradient_end": "#0077b6",
    "success": "#00ff88",
    "warning": "#ffcc00",
    "error": "#ff3366",
    "info": "#00e5ff",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── 日志系统配置 ──
LOG_SHARE_PATH = r"\\192.168.4.82\share\log"

def get_system_info():
    """获取系统信息：IP地址、计算机名"""
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
    except Exception:
        hostname = "未知"
        ip_address = "未知"
    return {
        "hostname": hostname,
        "ip_address": ip_address,
        "timestamp": datetime.now().isoformat(),
        "app_version": "v2.0"
    }


def _report_error(etype, evalue, tb):
    """未捕获异常的统一处理：写文件 + 弹窗（窗口版 exe 默认看不到 stderr）。"""
    text = "".join(traceback.format_exception(etype, evalue, tb))
    try:
        log_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "scan_gate_error.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("==== " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " ====\n" + text + "\n")
    except Exception:
        pass
    try:
        import tkinter.messagebox as _mb
        _mb.showerror("程序出错", text[-3000:])
    except Exception:
        pass
    print(text)

sys.excepthook = _report_error

def log_operation(operation_type, details, success=True):
    """记录操作日志：本地优先写入，best-effort 同步到网络共享（离线也不丢）"""
    try:
        system_info = get_system_info()
        log_entry = {
            **system_info,
            "operation": operation_type,
            "details": details,
            "success": success,
            "log_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        line = json.dumps(log_entry, ensure_ascii=False) + "\n"
        today = datetime.now().strftime("%Y-%m-%d")

        # 1) 始终写入本地日志（~/.printer_scan_logs），即使未连接共享也不丢失
        local_dir = os.path.join(os.path.expanduser("~"), ".printer_scan_logs")
        try:
            os.makedirs(local_dir, exist_ok=True)
            with open(os.path.join(local_dir, f"scan_gate_{today}.log"), "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

        # 2) best-effort 同步到网络共享日志
        #    ⚠️ 关键：UNC 路径(如 \\192.168.4.82\share\log)不可达时，os.path.exists/makedirs/open
        #    会被 Windows 网络重定向器阻塞 30~60 秒以上。必须放到后台守护线程，
        #    否则 __init__ 中的 log_operation("app_start") 会卡死主线程、mainloop 无法启动，
        #    表现为“窗口能显示但所有按钮点不动”。
        def _sync_network_log():
            try:
                if not os.path.exists(LOG_SHARE_PATH):
                    os.makedirs(LOG_SHARE_PATH, exist_ok=True)
                with open(os.path.join(LOG_SHARE_PATH, f"scan_gate_{today}.log"), "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass
        threading.Thread(target=_sync_network_log, daemon=True).start()

        return True
    except Exception as e:
        print(f"日志记录失败: {e}")
        return False


# ── 粒子系统 ──
class ParticleSystem:
    """背景粒子动画引擎"""
    def __init__(self, canvas, width, height, count=60):
        self.canvas = canvas
        self.w = width
        self.h = height
        self.particles = []
        self.lines = []
        self.connections = []
        self.running = False
        self.count = count
        
        for _ in range(count):
            self.particles.append({
                "x": random.uniform(0, width),
                "y": random.uniform(0, height),
                "vx": random.uniform(-0.3, 0.3),
                "vy": random.uniform(-0.3, 0.3),
                "size": random.uniform(1.0, 2.5),
                "opacity": random.uniform(0.3, 0.9),
                "pulse": random.uniform(0, 2 * math.pi),
                "pulse_speed": random.uniform(0.01, 0.04),
                "hue": random.choice(["cyan", "magenta", "blue", "white"]),
            })
        
    def _get_color(self, hue, opacity):
        if hue == "cyan":
            return f"#00e5ff{int(opacity*255):02x}" if opacity < 1 else "#00e5ff"
        elif hue == "magenta":
            return f"#ff00e5{int(opacity*255):02x}" if opacity < 1 else "#ff00e5"
        elif hue == "blue":
            return f"#448aff{int(opacity*255):02x}" if opacity < 1 else "#448aff"
        else:
            return f"#ffffff{int(opacity*255):02x}" if opacity < 1 else "#ffffff"

    def update(self):
        if not self.running:
            return
        
        self.canvas.delete("particle")
        
        # 更新粒子位置
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["pulse"] += p["pulse_speed"]
            
            # 边界反弹
            if p["x"] <= 0 or p["x"] >= self.w:
                p["vx"] *= -1
            if p["y"] <= 0 or p["y"] >= self.h:
                p["vy"] *= -1
                
            # 脉冲透明度
            alpha = p["opacity"] * (0.6 + 0.4 * math.sin(p["pulse"]))
            glow_size = p["size"] + 1.5 * (0.5 + 0.5 * math.sin(p["pulse"]))
            
            color = self._get_color(p["hue"], min(alpha, 1.0))
            
            # 发光粒子
            self.canvas.create_oval(
                p["x"] - glow_size, p["y"] - glow_size,
                p["x"] + glow_size, p["y"] + glow_size,
                fill=color, outline="", tags="particle"
            )
        
        # 绘制连线（近邻粒子之间）
        for i in range(len(self.particles)):
            for j in range(i + 1, len(self.particles)):
                p1 = self.particles[i]
                p2 = self.particles[j]
                dx = p1["x"] - p2["x"]
                dy = p1["y"] - p2["y"]
                dist = math.sqrt(dx * dx + dy * dy)
                
                if dist < 120:
                    alpha = 1.0 - (dist / 120)
                    alpha *= 0.15
                    self.canvas.create_line(
                        p1["x"], p1["y"], p2["x"], p2["y"],
                        fill=f"#00e5ff{int(alpha*255):02x}",
                        width=0.5, tags="particle"
                    )
        
        # 绘制网格线
        grid_spacing = 80
        grid_alpha = 0.04
        for x in range(grid_spacing, self.w, grid_spacing):
            self.canvas.create_line(
                x, 0, x, self.h,
                fill=f"#00e5ff{int(grid_alpha*255):02x}",
                width=0.5, tags="particle"
            )
        for y in range(grid_spacing, self.h, grid_spacing):
            self.canvas.create_line(
                0, y, self.w, y,
                fill=f"#00e5ff{int(grid_alpha*255):02x}",
                width=0.5, tags="particle"
            )
        
    def start(self):
        self.running = True
        
    def stop(self):
        self.running = False


# ── 发光按钮 ──
class NeonButton(ctk.CTkButton):
    """带脉冲发光特效的按钮。

    关键修复：CTkButton 把内部 canvas 的 <ButtonRelease-1> 绑定到 self._on_release，
    而 self._on_release 在多态下解析为「本类的override」。原实现只改了颜色、没有回调
    command，导致每个按钮点击都不触发任何逻辑（“点了没反应 / 全失效”）。
    这里让 override 在恢复视觉的同时真正调用 self._command()。

    注意：不要在本类里再 bind 一次 <ButtonRelease-1>（CTkButton.bind 会把绑定重定向到
    内部 canvas，重复 bind 会让 command 触发两次），也不要 unbind canvas 的 release
    （会把 CTkButton 的回调一起删掉，反而彻底失效）。"""
    def __init__(self, master, neon_color=CYBER_COLORS["neon_cyan"], **kwargs):
        self.neon_color = neon_color
        self._animation_phase = 0
        self._anim_running = False
        
        # 默认样式
        kwargs.setdefault("fg_color", "#151530")
        kwargs.setdefault("hover_color", "#1e1e40")
        kwargs.setdefault("text_color", neon_color)
        kwargs.setdefault("border_color", neon_color)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("font", ("Microsoft YaHei UI", 13))
        
        super().__init__(master, **kwargs)
        
        # 视觉绑定（Enter/Leave/Press）。<ButtonRelease-1> 由 CTkButton 已绑到本类的
        # _on_release（下方），无需重复绑定，避免 command 触发两次。
        self.bind("<Enter>", self._on_hover_in)
        self.bind("<Leave>", self._on_hover_out)
        self.bind("<Button-1>", self._on_press)
        
    def _on_hover_in(self, event):
        self.configure(border_width=2, fg_color="#1a1a3a")
        self._start_pulse()
        
    def _on_hover_out(self, event):
        self._anim_running = False
        self.configure(border_width=1, fg_color="#151530")
        
    def _on_press(self, event):
        self.configure(fg_color="#0a0a2a", border_width=2)
        
    def _on_release(self, event=None):
        # CTkButton 内部 canvas 的 <ButtonRelease-1> 会调用本方法；
        # 恢复视觉的同时，真正触发用户传入的 command。
        self.configure(fg_color="#1a1a3a", border_width=2)
        if self._mouse_inside and str(self._state) != "disabled":
            if self._command is not None:
                self._command()
        
    def _start_pulse(self):
        if self._anim_running:
            return
        self._anim_running = True
        self._pulse()
        
    def _pulse(self):
        if not self._anim_running:
            return
        import colorsys
        import math
        self._animation_phase += 0.05
        val = 0.7 + 0.3 * math.sin(self._animation_phase)
        r, g, b = self._hex_to_rgb(self.neon_color)
        r, g, b = int(r * val), int(g * val), int(b * val)
        self.configure(border_color=f"#{r:02x}{g:02x}{b:02x}")
        self.after(30, self._pulse)
        
    @staticmethod
    def _hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


# ── 霓虹开关 ──
class NeonSwitch(ctk.CTkSwitch):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("text_color", CYBER_COLORS["text_primary"])
        kwargs.setdefault("font", ("Microsoft YaHei UI", 13))
        kwargs.setdefault("progress_color", CYBER_COLORS["neon_cyan"])
        super().__init__(master, **kwargs)


# ── 霓虹输入框 ──
class NeonEntry(ctk.CTkEntry):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", CYBER_COLORS["bg_input"])
        kwargs.setdefault("border_color", CYBER_COLORS["border_glow"])
        kwargs.setdefault("text_color", CYBER_COLORS["text_primary"])
        kwargs.setdefault("font", ("Microsoft YaHei UI", 13))
        super().__init__(master, **kwargs)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        
    def _on_focus_in(self, event):
        self.configure(border_color=CYBER_COLORS["neon_cyan"])
        self._animate_focus(0)
        
    def _on_focus_out(self, event):
        self.configure(border_color=CYBER_COLORS["border_glow"])
        
    def _animate_focus(self, step):
        if step >= 20:
            return
        alpha = 0.3 + 0.7 * math.sin(step * 0.3)
        r = int(0x00 * (1 - alpha) + 0xe5 * alpha)
        g = int(0x00 * (1 - alpha) + 0xff * alpha)
        self.configure(border_color=f"#{r:02x}{g:02x}ff")
        if self.focus_get() == self:
            self.after(15, lambda: self._animate_focus(step + 1))


# ── 主应用程序 ──


# ── 单实例守护 ──
# 避免反复双击导致多个进程堆积，互相抢占磁盘/CPU，加剧“打开无响应”。
_INSTANCE_MUTEX = None

def _is_already_running():
    """返回 True 表示已有实例在运行（本进程应退出）。"""
    global _INSTANCE_MUTEX
    try:
        if sys.platform.startswith("win"):
            kernel32 = ctypes.windll.kernel32
            _INSTANCE_MUTEX = kernel32.CreateMutexW(None, 0, "SCAN_GATE_PRINTER_TOOL_INSTANCE")
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                return True
    except Exception:
        pass
    return False

def _show_already_running():
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "SCAN.GATE 已在运行中，请勿重复打开。",
            "提示",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass

class CyberPrinterApp:
    def __init__(self):
        # 根窗口改用 customtkinter.CTk（官方推荐、按钮点击最稳定）
        self.root = ctk.CTk()
        # 把 Tk 内部的回调异常也导向统一处理（按钮点击里抛的异常默认只进 stderr）
        self.root.report_callback_exception = _report_error
        self.root.title("SCAN.GATE // 打印机扫描终端 v2.0")
        # 先按目标尺寸设好，再基于屏幕尺寸居中（夹取在屏幕内，避免窗口跑出可视区）
        self.root.geometry("1440x820")
        self.root.minsize(1200, 640)
        self.root.update_idletasks()
        _sw = self.root.winfo_screenwidth()
        _sh = self.root.winfo_screenheight()
        _w = min(1440, _sw - 40)
        _h = min(820, _sh - 60)
        _x = max(0, (_sw - _w) // 2)
        _y = max(0, (_sh - _h) // 2)
        self.root.geometry(f"{_w}x{_h}+{_x}+{_y}")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        
        # 设置图标（兼容 onefile(_MEIPASS) 与 one-folder(同目录) 两种打包）
        if getattr(sys, 'frozen', False):
            _base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            icon_path = os.path.join(_base, "scan_gate_icon.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_gate_icon.ico")
        try:
            self.root.iconbitmap(icon_path)
        except Exception:
            pass
        
        # 设置背景色（customtkinter CTk 根原生支持 fg_color）
        self.root.configure(fg_color=CYBER_COLORS["bg_primary"])
        self.share_path = r"\\192.168.4.82\share\PDF"
        self.username = "share"
        self.password = "share"
        
        # 日志历史
        self.log_history = deque(maxlen=200)
        
        self._file_checkboxes = {}   # {name: BooleanVar}
        self._file_data = {}          # {name: (ftype, size, mtime, ext)}
        
        # 配置存储
        self.config_file = os.path.join(os.path.expanduser("~"), ".printer_scan_config.json")
        self.saved_connections = []  # 保存的连接列表
        self.default_connection = None  # 默认连接索引
        self._load_config()
        
        # 构建UI
        self._build_ui()
        
        # 延迟启动动画循环
        self._animation_running = True
        self.root.after(100, self._start_animations)  # 延迟100ms启动动画
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 记录应用启动
        log_operation("app_start", {
            "version": "v2.0",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    def _start_animations(self):
        """延迟启动动画，提高启动速度"""
        self._animate()
        # 延迟更新状态栏时间
        self.root.after(500, self._update_time)
    
    def _update_time(self):
        """更新状态栏时间"""
        if hasattr(self, 'time_label'):
            self.time_label.configure(text=datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._update_time)
        
    # ── UI构建 ──
    def _build_ui(self):
        # 主容器
        self.main_frame = ctk.CTkFrame(
            self.root, fg_color="transparent"
        )
        self.main_frame.pack(fill="both", expand=True, padx=3, pady=3)
        
        # 顶部标题栏
        self._build_header()
        
        # 中部内容区（左：配置+控制 / 右：文件列表）
        content = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        
        content.grid_columnconfigure(0, weight=0, minsize=360)
        content.grid_columnconfigure(1, weight=1)
        content.grid_columnconfigure(2, weight=0, minsize=400)
        content.grid_rowconfigure(0, weight=1)
        
        # 左侧面板（控制区）
        left_panel = ctk.CTkFrame(content, fg_color=CYBER_COLORS["bg_card"], corner_radius=12)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._build_left_panel(left_panel)
        
        # 中间面板（文件浏览器）
        middle_panel = ctk.CTkFrame(content, fg_color=CYBER_COLORS["bg_card"], corner_radius=12)
        middle_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self._build_right_panel(middle_panel)
        
        # 右侧面板（文件预览）
        preview_panel = ctk.CTkFrame(content, fg_color=CYBER_COLORS["bg_card"], corner_radius=12)
        preview_panel.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        self._build_preview_panel(preview_panel)
        
        # 底部状态栏
        self._build_status_bar()
        
    def _build_header(self):
        header = ctk.CTkFrame(
            self.main_frame, fg_color=CYBER_COLORS["bg_card"],
            corner_radius=12, height=56
        )
        header.pack(fill="x", padx=6, pady=(6, 4))
        header.pack_propagate(False)
        
        # 左侧标题
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", padx=16, pady=8)
        
        # 扫描线图标动画
        self.scan_icon = ctk.CTkLabel(
            title_frame, text="◈", font=("Segoe UI Symbol", 22),
            text_color=CYBER_COLORS["neon_cyan"]
        )
        self.scan_icon.pack(side="left", padx=(0, 8))
        
        ctk.CTkLabel(
            title_frame, text="SCAN.GATE // 打印机扫描终端",
            font=("Microsoft YaHei UI", 17, "bold"),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack(side="left")
        
        # 版本标签
        ctk.CTkLabel(
            title_frame, text="v2.0",
            font=("Cascadia Code", 10),
            text_color=CYBER_COLORS["text_dim"]
        ).pack(side="left", padx=(8, 0))
        
        # 右侧状态指示
        self.connection_indicator = ctk.CTkLabel(
            header, text="● 未连接",
            font=("Microsoft YaHei UI", 12),
            text_color=CYBER_COLORS["text_dim"]
        )
        self.connection_indicator.pack(side="right", padx=16)
        
        self.time_label = ctk.CTkLabel(
            header, text="", font=("Microsoft YaHei UI", 12),
            text_color=CYBER_COLORS["text_secondary"]
        )
        self.time_label.pack(side="right", padx=8)
        
    def _build_left_panel(self, parent):
        # 配置区标题
        self._section_label(parent, "// 连接配置", CYBER_COLORS["neon_cyan"]).pack(
            anchor="w", padx=16, pady=(14, 8)
        )
        
        # 共享路径
        ctk.CTkLabel(
            parent, text="共享路径", font=("Microsoft YaHei UI", 12),
            text_color=CYBER_COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(4, 2))
        
        self.share_entry = NeonEntry(parent, width=340, height=34)
        self.share_entry.insert(0, self.share_path)
        self.share_entry.pack(fill="x", padx=16, pady=(0, 8))
        
        # 凭据行
        cred_frame = ctk.CTkFrame(parent, fg_color="transparent")
        cred_frame.pack(fill="x", padx=16, pady=(0, 4))
        cred_frame.grid_columnconfigure(0, weight=1)
        cred_frame.grid_columnconfigure(1, weight=1)
        
        # 用户名
        user_col = ctk.CTkFrame(cred_frame, fg_color="transparent")
        user_col.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(
            user_col, text="用户名", font=("Microsoft YaHei UI", 12),
            text_color=CYBER_COLORS["text_secondary"]
        ).pack(anchor="w")
        self.user_entry = NeonEntry(user_col, width=160, height=34)
        self.user_entry.insert(0, self.username)
        self.user_entry.pack(fill="x")
        
        # 密码
        pass_col = ctk.CTkFrame(cred_frame, fg_color="transparent")
        pass_col.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(
            pass_col, text="密码", font=("Microsoft YaHei UI", 12),
            text_color=CYBER_COLORS["text_secondary"]
        ).pack(anchor="w")
        self.pass_entry = NeonEntry(pass_col, width=160, height=34, show="●")
        self.pass_entry.insert(0, self.password)
        self.pass_entry.pack(fill="x")
        
        # 操作按钮区
        self._section_label(parent, "// 操作面板", CYBER_COLORS["neon_magenta"]).pack(
            anchor="w", padx=16, pady=(16, 8)
        )
        
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16)
        
        # 连接按钮
        self.btn_connect = NeonButton(
            btn_frame, text="▸ 连接共享", width=160,
            neon_color=CYBER_COLORS["neon_green"],
            command=self.connect_share
        )
        self.btn_connect.pack(fill="x", pady=(0, 6))
        
        # 断开按钮
        self.btn_disconnect = NeonButton(
            btn_frame, text="◂ 断开连接", width=160,
            neon_color=CYBER_COLORS["neon_red"],
            command=self.disconnect_share
        )
        self.btn_disconnect.pack(fill="x", pady=(0, 6))
        
        # 打开文件夹按钮
        self.btn_open = NeonButton(
            btn_frame, text="⏏ 打开文件夹", width=160,
            neon_color=CYBER_COLORS["neon_blue"],
            command=self.open_folder
        )
        self.btn_open.pack(fill="x", pady=(0, 6))
        
        # 测试连接按钮
        self.btn_test = NeonButton(
            btn_frame, text="↻ 测试连接", width=160,
            neon_color=CYBER_COLORS["neon_yellow"],
            command=self.test_connection
        )
        self.btn_test.pack(fill="x", pady=(0, 6))
        
        # 文件操作按钮
        self._section_label(parent, "// 文件操作", CYBER_COLORS["neon_green"]).pack(
            anchor="w", padx=16, pady=(16, 8)
        )
        
        op_frame = ctk.CTkFrame(parent, fg_color="transparent")
        op_frame.pack(fill="x", padx=16)
        
        row1 = ctk.CTkFrame(op_frame, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 4))
        row1.grid_columnconfigure(0, weight=1)
        row1.grid_columnconfigure(1, weight=1)
        
        NeonButton(
            row1, text="↑ 上传文件", neon_color=CYBER_COLORS["neon_cyan"],
            command=self.upload_file
        ).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        
        NeonButton(
            row1, text="↓ 下载文件", neon_color=CYBER_COLORS["neon_cyan"],
            command=self.download_file
        ).grid(row=0, column=1, sticky="ew", padx=(2, 0))
        
        row2 = ctk.CTkFrame(op_frame, fg_color="transparent")
        row2.pack(fill="x")
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=1)
        
        NeonButton(
            row2, text="↺ 刷新列表", neon_color=CYBER_COLORS["neon_blue"],
            command=self.refresh_file_list
        ).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        
        NeonButton(
            row2, text="✕ 删除文件", neon_color=CYBER_COLORS["neon_red"],
            command=self.delete_file
        ).grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # 返回上级目录
        row3 = ctk.CTkFrame(op_frame, fg_color="transparent")
        row3.pack(fill="x", pady=(4, 0))
        row3.grid_columnconfigure(0, weight=1)
        NeonButton(
            row3, text="⤴ 返回上级目录", neon_color=CYBER_COLORS["neon_blue"],
            command=self._go_up
        ).grid(row=0, column=0, sticky="ew")
        
        # 统计信息区
        self._section_label(parent, "// 会话状态", CYBER_COLORS["neon_yellow"]).pack(
            anchor="w", padx=16, pady=(16, 8)
        )
        
        stats_frame = ctk.CTkFrame(
            parent, fg_color=CYBER_COLORS["bg_input"], corner_radius=8
        )
        stats_frame.pack(fill="x", padx=16, pady=(0, 12))
        
        self.stats_labels = {}
        for key, label in [("files", "文件数"), ("size", "总大小"), ("conn", "连接状态")]:
            row = ctk.CTkFrame(stats_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(
                row, text=label, font=("Microsoft YaHei UI", 12),
                text_color=CYBER_COLORS["text_dim"], width=60
            ).pack(side="left")
            lbl = ctk.CTkLabel(
                row, text="--", font=("Microsoft YaHei UI", 13, "bold"),
                text_color=CYBER_COLORS["neon_cyan"]
            )
            lbl.pack(side="left", padx=(8, 0))
            self.stats_labels[key] = lbl
            
        # 关于按钮
        NeonButton(
            parent, text="ℹ 关于程序", neon_color=CYBER_COLORS["neon_magenta"],
            command=self._show_about
        ).pack(fill="x", padx=16, pady=(4, 8))
        
        # 隐藏的Canvas用于特效
        self.effect_canvas = None
        
    def _build_right_panel(self, parent):
        # 工具栏
        toolbar = ctk.CTkFrame(parent, fg_color="transparent", height=36)
        toolbar.pack(fill="x", padx=12, pady=(10, 4))
        toolbar.pack_propagate(False)
        
        ctk.CTkLabel(
            toolbar, text="// 文件浏览器", font=("Microsoft YaHei UI", 14, "bold"),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack(side="left")
        
        # 设置按钮
        self.settings_btn = ctk.CTkButton(
            toolbar, text="⚙", font=("Segoe UI Symbol", 16),
            fg_color="transparent", hover_color=CYBER_COLORS["bg_input"],
            width=40, height=30, command=self._show_settings
        )
        self.settings_btn.pack(side="right", padx=(0, 8))
        
        # 当前路径
        self.path_label = ctk.CTkLabel(
            toolbar, text="", font=("Cascadia Code", 10),
            text_color=CYBER_COLORS["text_dim"]
        )
        self.path_label.pack(side="right")
        
        # 路径面包屑
        ctk.CTkLabel(
            toolbar, text="", font=("Cascadia Code", 9),
            text_color=CYBER_COLORS["text_secondary"]
        ).pack(side="right", padx=(0, 8))
        
        # 文件列表
        list_frame = ctk.CTkFrame(
            parent, fg_color=CYBER_COLORS["bg_input"], corner_radius=8
        )
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        
        # 列表头
        header_frame = ctk.CTkFrame(list_frame, fg_color="transparent", height=30)
        header_frame.pack(fill="x", padx=8, pady=(6, 0))
        header_frame.pack_propagate(False)
        
        # 全选复选框
        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_cb = ctk.CTkCheckBox(
            header_frame, text="", variable=self.select_all_var, width=22,
            fg_color=CYBER_COLORS["neon_cyan"], hover_color=CYBER_COLORS["neon_cyan"],
            border_color=CYBER_COLORS["text_dim"], border_width=1,
            command=self._toggle_select_all
        )
        self.select_all_cb.pack(side="left", padx=( 8, 0))
        
        cols = [("文件名", 350), ("大小", 100), ("修改时间", 160), ("类型", 80)]
        for text, width in cols:
            ctk.CTkLabel(
                header_frame, text=text, font=("Microsoft YaHei UI", 12, "bold"),
                text_color=CYBER_COLORS["text_dim"]
            ).pack(side="left", padx=(0, 8), ipadx=0)
        
        # 删除选中按钮
        self.delete_selected_btn = ctk.CTkButton(
            header_frame, text="删除选中", font=("Microsoft YaHei UI", 11),
            fg_color=CYBER_COLORS["neon_red"], hover_color=CYBER_COLORS["neon_red"],
            width=70, height=26, command=self._delete_selected_files
        )
        self.delete_selected_btn.pack(side="right", padx=(0, 4))
        
        # 滚动文件列表
        self.file_scroll = ctk.CTkScrollableFrame(
            list_frame, fg_color="transparent",
            scrollbar_button_color=CYBER_COLORS["neon_cyan"],
            scrollbar_button_hover_color=CYBER_COLORS["neon_magenta"]
        )
        self.file_scroll.pack(fill="both", expand=True, padx=4, pady=4)
        
        # 拖拽上传（tkinterdnd2）已于本次修复移除：
        #   原 TkinterDnD.Tk() 根窗口与 customtkinter 6.x 的 CTkButton 命令绑定冲突，
        #   导致“所有按钮点不动 / 连接共享点了没反应”。现改用 customtkinter.CTk 作根，
        #   点击恢复正常；拖拽上传由「↑ 上传文件」按钮（filedialog）替代。
        #   如需恢复拖拽，可在 CTk 根上用 TkinterDnD.require(self.root) 兼容方案再接回，
        #   相关方法 _on_drag_drop_upload / _upload_dragged_file 已保留备用。
        
        # 日志区
        log_section = ctk.CTkFrame(parent, fg_color=CYBER_COLORS["bg_input"], corner_radius=8, height=150)
        log_section.pack(fill="x", padx=12, pady=(4, 10))
        log_section.pack_propagate(False)
        
        log_header = ctk.CTkFrame(log_section, fg_color="transparent", height=26)
        log_header.pack(fill="x", padx=8, pady=(4, 0))
        log_header.pack_propagate(False)
        ctk.CTkLabel(
            log_header, text="// 终端日志", font=("Microsoft YaHei UI", 12, "bold"),
            text_color=CYBER_COLORS["text_dim"]
        ).pack(side="left")
        
        self.log_text = ctk.CTkTextbox(
            log_section, fg_color="transparent",
            text_color=CYBER_COLORS["text_secondary"],
            font=("Microsoft YaHei UI", 11),
            activate_scrollbars=False,
            border_width=0
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=4)
        self.log_text.configure(state="disabled")
        
    def _build_preview_panel(self, parent):
        """右侧文件预览面板：单击文件列表中的图片/PDF 即在此渲染预览"""
        # 标题栏
        header = ctk.CTkFrame(parent, fg_color="transparent", height=36)
        header.pack(fill="x", padx=12, pady=(10, 4))
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="// 文件预览", font=("Microsoft YaHei UI", 14, "bold"),
            text_color=CYBER_COLORS["neon_magenta"]
        ).pack(side="left")
        self.preview_open_btn = NeonButton(
            header, text="↗ 打开", neon_color=CYBER_COLORS["neon_green"],
            command=self._open_previewed_file
        )
        self.preview_open_btn.pack(side="right", padx=(0, 8))
        try:
            self.preview_open_btn.configure(state="disabled")
        except Exception:
            pass

        # 预览主体（可滚动，适配大图）
        self.preview_scroll = ctk.CTkScrollableFrame(
            parent, fg_color=CYBER_COLORS["bg_input"], corner_radius=8
        )
        self.preview_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        # 面板尺寸变化时按当前宽度重新适配图片
        self.preview_scroll.bind("<Configure>", lambda e: self._render_preview())

        # 文件信息区
        self.preview_info = ctk.CTkFrame(
            parent, fg_color=CYBER_COLORS["bg_input"], corner_radius=8, height=120
        )
        self.preview_info.pack(fill="x", padx=12, pady=(4, 10))
        self.preview_info.pack_propagate(False)
        self.preview_name = ctk.CTkLabel(
            self.preview_info, text="—", font=("Cascadia Code", 12, "bold"),
            text_color=CYBER_COLORS["neon_cyan"], anchor="w"
        )
        self.preview_name.pack(anchor="w", padx=10, pady=(8, 2))
        self.preview_meta = ctk.CTkLabel(
            self.preview_info, text="尚未选择文件", font=("Microsoft YaHei UI", 11),
            text_color=CYBER_COLORS["text_secondary"], anchor="w"
        )
        self.preview_meta.pack(anchor="w", padx=10, pady=(0, 8))

        # 预览状态
        self._preview_mode = "none"      # none / loading / image / info
        self._preview_pil = None         # 当前预览的 PIL 原图
        self._preview_image = None       # 当前 CTkImage 引用（防 GC）
        self._preview_path = None        # 当前预览文件的完整路径
        self._preview_loading_text = ""
        self._render_preview()

    def _build_status_bar(self):
        status = ctk.CTkFrame(
            self.main_frame, fg_color=CYBER_COLORS["bg_card"],
            corner_radius=8, height=28
        )
        status.pack(fill="x", padx=6, pady=(0, 6))
        status.pack_propagate(False)
        
        self.status_label = ctk.CTkLabel(
            status, text="[ 就绪 ] 等待操作...",
            font=("Microsoft YaHei UI", 12),
            text_color=CYBER_COLORS["neon_cyan"]
        )
        self.status_label.pack(side="left", padx=12)
        
    @staticmethod
    def _section_label(parent, text, color):
        return ctk.CTkLabel(
            parent, text=text, font=("Microsoft YaHei UI", 13, "bold"),
            text_color=color
        )
        
    # ── 动画系统 ──
    def _animate(self):
        """主动画循环（精简版，提高性能）"""
        if not self._animation_running:
            return
        
        # 扫描图标旋转（模拟）
        self._icon_frame = getattr(self, "_icon_frame", 0) + 1
        icons = ["◈", "◇", "◆", "◇"]
        self.scan_icon.configure(text=icons[self._icon_frame % 4])
        
        # 状态栏脉冲
        self._status_pulse = getattr(self, "_status_pulse", 0) + 0.06
        pulse_val = 0.7 + 0.3 * math.sin(self._status_pulse)
        r, g, b = 0, 229, 255
        r, g, b = int(r * pulse_val), int(g * pulse_val), int(b * pulse_val)
        self.status_label.configure(text_color=f"#{r:02x}{g:02x}{b:02x}")
        
        self.root.after(100, self._animate)  # 50ms → 100ms，减少一半调用频率
        
    # ── 配置持久化 ──
    def _load_config(self):
        """从文件加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.saved_connections = data.get("connections", [])
                self.default_connection = data.get("default", None)
                return
        except Exception:
            pass
        # 默认连接（与运行时默认共享一致）
        self.saved_connections = [
            {
                "name": "默认打印机",
                "share_path": r"\\192.168.4.82\share\PDF",
                "username": "share",
                "password": "share"
            }
        ]
        self.default_connection = 0
    
    def _save_config(self):
        """保存配置到文件"""
        data = {
            "connections": self.saved_connections,
            "default": self.default_connection
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _get_default_connection(self):
        """获取默认连接信息"""
        if self.default_connection is not None and 0 <= self.default_connection < len(self.saved_connections):
            return self.saved_connections[self.default_connection]
        return None
    
    # ── 设置页面 ──
    def _show_settings(self):
        """显示设置对话框"""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("连接设置")
        dialog.geometry("600x500")
        dialog.resizable(False, False)
        dialog.configure(fg_color=CYBER_COLORS["bg_primary"])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 居中
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 500) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 标题
        ctk.CTkLabel(
            main_frame, text="★ 已保存的连接配置", font=("Microsoft YaHei UI", 16, "bold"),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack(anchor="w", pady=(0, 12))
        
        # 连接列表（可滚动）
        list_frame = ctk.CTkScrollableFrame(
            main_frame, fg_color=CYBER_COLORS["bg_input"], corner_radius=8,
            height=240
        )
        list_frame.pack(fill="x", pady=(0, 12))
        
        self._refresh_connection_list(list_frame, dialog)
        
        # 添加新连接按钮
        ctk.CTkButton(
            main_frame, text="+ 添加新连接", font=("Microsoft YaHei UI", 13),
            fg_color=CYBER_COLORS["neon_magenta"], text_color="#0a0a0f",
            hover_color="#dd33aa", height=36,
            command=lambda: self._add_connection_dialog(dialog, list_frame)
        ).pack(fill="x", pady=(0, 20))
        
        ctk.CTkButton(
            dialog, text="关闭", font=("Microsoft YaHei UI", 13),
            fg_color=CYBER_COLORS["bg_input"], text_color=CYBER_COLORS["text_secondary"],
            hover_color=CYBER_COLORS["bg_card"], height=36,
            command=dialog.destroy
        ).pack(pady=(0, 15))
    
    def _refresh_connection_list(self, list_frame, dialog):
        """刷新连接列表"""
        for widget in list_frame.winfo_children():
            widget.destroy()
        
        conn = self._get_default_connection()
        default_idx = self.default_connection
        
        for i, entry in enumerate(self.saved_connections):
            is_default = (i == default_idx)
            item_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
            item_frame.pack(fill="x", padx=8, pady=3)
            
            # 星标 / 设为默认
            star_text = "★" if is_default else "☆"
            star_color = CYBER_COLORS["neon_cyan"] if is_default else CYBER_COLORS["text_dim"]
            ctk.CTkButton(
                item_frame, text=star_text, font=("Microsoft YaHei UI", 14, "bold"),
                fg_color="transparent", text_color=star_color,
                hover_color=CYBER_COLORS["bg_card"], width=34, height=28,
                command=lambda idx=i: self._set_default(idx, list_frame, dialog)
            ).pack(side="left", padx=(0, 6))
            
            # 名称 + 路径
            info = f"{entry['name']}  [{entry['share_path']}]"
            ctk.CTkLabel(
                item_frame, text=info, font=("Microsoft YaHei UI", 12),
                text_color=CYBER_COLORS["text_primary"], anchor="w"
            ).pack(side="left", fill="x", expand=True)
            
            # 操作按钮
            ctk.CTkButton(
                item_frame, text="编辑", font=("Microsoft YaHei UI", 11),
                fg_color="transparent", text_color=CYBER_COLORS["neon_green"],
                hover_color=CYBER_COLORS["bg_card"], width=46, height=26,
                command=lambda idx=i: self._edit_connection_dialog(idx, list_frame, dialog)
            ).pack(side="right", padx=2)
            
            ctk.CTkButton(
                item_frame, text="删除", font=("Microsoft YaHei UI", 11),
                fg_color="transparent", text_color=CYBER_COLORS["neon_magenta"],
                hover_color=CYBER_COLORS["bg_card"], width=46, height=26,
                command=lambda idx=i: self._delete_connection(idx, list_frame, dialog)
            ).pack(side="right", padx=2)
    
    def _set_default(self, idx, list_frame, dialog):
        """设置默认连接"""
        self.default_connection = idx
        self._save_config()
        self._fill_from_connection()
        self._refresh_connection_list(list_frame, dialog)
        self._show_toast(f"已将「{self.saved_connections[idx]['name']}」设为默认连接",
                        color=CYBER_COLORS["neon_green"])
    
    def _delete_connection(self, idx, list_frame, dialog):
        """删除连接"""
        if len(self.saved_connections) <= 1:
            self._show_toast("至少保留一个连接", color=CYBER_COLORS["neon_magenta"])
            return
        name = self.saved_connections[idx]["name"]
        self.saved_connections.pop(idx)
        if self.default_connection == idx:
            self.default_connection = 0
        elif self.default_connection is not None and self.default_connection > idx:
            self.default_connection -= 1
        self._save_config()
        self._fill_from_connection()
        self._refresh_connection_list(list_frame, dialog)
        self._show_toast(f"已删除连接「{name}」", color=CYBER_COLORS["neon_magenta"])
    
    def _add_connection_dialog(self, parent_dialog, list_frame):
        """添加新连接对话框"""
        self._connection_form("添加新连接", None, parent_dialog, list_frame)
    
    def _edit_connection_dialog(self, idx, list_frame, parent_dialog):
        """编辑连接对话框"""
        entry = self.saved_connections[idx]
        self._connection_form("编辑连接", idx, parent_dialog, list_frame)
    
    def _connection_form(self, title, idx, parent_dialog, list_frame):
        """连接表单通用对话框"""
        is_edit = idx is not None
        entry = self.saved_connections[idx] if is_edit else {"name": "", "share_path": "", "username": "", "password": ""}
        
        form = ctk.CTkToplevel(parent_dialog)
        form.title(title)
        form.geometry("500x550")
        form.resizable(False, False)
        form.configure(fg_color=CYBER_COLORS["bg_primary"])
        form.transient(parent_dialog)
        form.grab_set()
        
        # 居中
        form.update_idletasks()
        px = parent_dialog.winfo_x() + (parent_dialog.winfo_width() - 500) // 2
        py = parent_dialog.winfo_y() + (parent_dialog.winfo_height() - 550) // 2
        form.geometry(f"+{px}+{py}")
        
        # 主滚动容器
        scroll_container = ctk.CTkScrollableFrame(
            form, fg_color="transparent", height=510
        )
        scroll_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 标题
        ctk.CTkLabel(
            scroll_container, text=title, font=("Microsoft YaHei UI", 16, "bold"),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack(anchor="w", pady=(0, 20))
        
        # 名称
        ctk.CTkLabel(scroll_container, text="连接名称", font=("Microsoft YaHei UI", 13),
                    text_color=CYBER_COLORS["text_secondary"]).pack(anchor="w")
        name_entry = ctk.CTkEntry(scroll_container, font=("Microsoft YaHei UI", 14), height=40,
                                  fg_color=CYBER_COLORS["bg_input"],
                                  text_color=CYBER_COLORS["text_primary"])
        name_entry.pack(fill="x", pady=(6, 15))
        name_entry.insert(0, entry["name"])
        
        # 共享路径
        ctk.CTkLabel(scroll_container, text="共享路径", font=("Microsoft YaHei UI", 13),
                    text_color=CYBER_COLORS["text_secondary"]).pack(anchor="w")
        path_entry = ctk.CTkEntry(scroll_container, font=("Microsoft YaHei UI", 14), height=40,
                                  fg_color=CYBER_COLORS["bg_input"],
                                  text_color=CYBER_COLORS["text_primary"])
        path_entry.pack(fill="x", pady=(6, 15))
        path_entry.insert(0, entry["share_path"])
        
        # 用户名
        ctk.CTkLabel(scroll_container, text="用户名", font=("Microsoft YaHei UI", 13),
                    text_color=CYBER_COLORS["text_secondary"]).pack(anchor="w")
        user_entry = ctk.CTkEntry(scroll_container, font=("Microsoft YaHei UI", 14), height=40,
                                  fg_color=CYBER_COLORS["bg_input"],
                                  text_color=CYBER_COLORS["text_primary"])
        user_entry.pack(fill="x", pady=(6, 15))
        user_entry.insert(0, entry["username"])
        
        # 密码
        ctk.CTkLabel(scroll_container, text="密码", font=("Microsoft YaHei UI", 13),
                    text_color=CYBER_COLORS["text_secondary"]).pack(anchor="w")
        pwd_entry = ctk.CTkEntry(scroll_container, font=("Microsoft YaHei UI", 14), height=40,
                                 fg_color=CYBER_COLORS["bg_input"], show="•",
                                 text_color=CYBER_COLORS["text_primary"])
        pwd_entry.pack(fill="x", pady=(6, 20))
        pwd_entry.insert(0, entry["password"])
        
        # 测试连接按钮
        test_result_label = ctk.CTkLabel(
            scroll_container, text="", font=("Microsoft YaHei UI", 12),
            text_color=CYBER_COLORS["text_dim"]
        )
        test_result_label.pack(anchor="w", pady=(0, 20))
        
        def test_connection():
            name = name_entry.get().strip()
            path = path_entry.get().strip()
            user = user_entry.get().strip()
            pwd = pwd_entry.get().strip()
            
            if not path:
                test_result_label.configure(text="请输入共享路径", text_color=CYBER_COLORS["neon_red"])
                return
            
            test_result_label.configure(text="正在测试连接...", text_color=CYBER_COLORS["neon_cyan"])
            form.update()
            
            def _test():
                try:
                    # 先断开现有连接
                    subprocess.run(["net", "use", path, "/delete", "/y"],
                                 shell=False, capture_output=True,
                                 creationflags=CREATE_NO_WINDOW)
                    # 建立新连接
                    result = subprocess.run(
                        ["net", "use", path, pwd, f"/user:{user}", "/persistent:no"],
                        shell=False, capture_output=True, text=True,
                        creationflags=CREATE_NO_WINDOW
                    )
                    form.after(0, lambda: _on_test_result(result, path))
                except Exception as e:
                    form.after(0, lambda: test_result_label.configure(
                        text=f"测试异常: {str(e)}", text_color=CYBER_COLORS["neon_red"]
                    ))
            
            def _on_test_result(result, share_path):
                if result.returncode == 0:
                    test_result_label.configure(
                        text=f"✓ 连接测试成功: {share_path}", 
                        text_color=CYBER_COLORS["neon_green"]
                    )
                    # 测试后断开连接
                    subprocess.run(["net", "use", share_path, "/delete", "/y"],
                                 shell=False, capture_output=True,
                                 creationflags=CREATE_NO_WINDOW)
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    test_result_label.configure(
                        text=f"✗ 连接失败: {error_msg[:80]}", 
                        text_color=CYBER_COLORS["neon_red"]
                    )
            
            threading.Thread(target=_test, daemon=True).start()
        
        test_btn_frame = ctk.CTkFrame(scroll_container, fg_color="transparent")
        test_btn_frame.pack(fill="x", pady=(0, 20))
        
        ctk.CTkButton(
            test_btn_frame, text="测试连接", font=("Microsoft YaHei UI", 13),
            fg_color=CYBER_COLORS["neon_blue"], text_color="#0a0a0f",
            hover_color="#3366ff", height=36, width=100,
            command=test_connection
        ).pack(side="left")
        
        def save():
            name = name_entry.get().strip()
            path = path_entry.get().strip()
            user = user_entry.get().strip()
            pwd = pwd_entry.get().strip()
            
            if not name:
                self._show_toast("请输入连接名称", color=CYBER_COLORS["neon_magenta"])
                return
            if not path:
                self._show_toast("请输入共享路径", color=CYBER_COLORS["neon_magenta"])
                return
            
            new_entry = {"name": name, "share_path": path, "username": user, "password": pwd}
            if is_edit:
                self.saved_connections[idx] = new_entry
            else:
                self.saved_connections.append(new_entry)
                # 如果是第一个连接，设为默认
                if self.default_connection is None:
                    self.default_connection = 0
            
            self._save_config()
            self._fill_from_connection()
            form.destroy()
            self._refresh_connection_list(list_frame, parent_dialog)
            self._show_toast(f"连接「{name}」已{'更新' if is_edit else '添加'}",
                            color=CYBER_COLORS["neon_green"])
        
        # 底部按钮区域
        btn_frame = ctk.CTkFrame(scroll_container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(
            btn_frame, text="保存", font=("Microsoft YaHei UI", 14),
            fg_color=CYBER_COLORS["neon_green"], text_color="#0a0a0f",
            hover_color="#00cc88", height=40, width=100, command=save
        ).pack(side="right", padx=(10, 0))
        
        ctk.CTkButton(
            btn_frame, text="取消", font=("Microsoft YaHei UI", 14),
            fg_color=CYBER_COLORS["bg_input"], text_color=CYBER_COLORS["text_secondary"],
            hover_color=CYBER_COLORS["bg_card"], height=40, width=100,
            command=form.destroy
        ).pack(side="right")
    
    def _fill_from_connection(self):
        """从默认连接填充表单"""
        conn = self._get_default_connection()
        if conn:
            self.share_entry.delete(0, "end")
            self.share_entry.insert(0, conn["share_path"])
            self.user_entry.delete(0, "end")
            self.user_entry.insert(0, conn["username"])
            self.pass_entry.delete(0, "end")
            self.pass_entry.insert(0, conn["password"])
        
    def _on_close(self):
        # 记录应用关闭
        log_operation("app_shutdown", {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self._animation_running = False
        self.root.destroy()
        
    # ── 涟漪点击特效 ──
    def _ripple_effect(self, widget, color=CYBER_COLORS["neon_cyan"]):
        """在widget上产生涟漪效果"""
        try:
            x = widget.winfo_pointerx() - widget.winfo_rootx()
            y = widget.winfo_pointery() - widget.winfo_rooty()
        except Exception:
            x, y = 50, 20
            
        # 如果widget有canvas属性则用canvas，否则使用全局特效
        canvas = getattr(self, "effect_canvas", None)
        if canvas is None:
            return
            
        ripple_count = 3
        for i in range(ripple_count):
            delay = i * 80
            self._draw_ripple(canvas, x, y, delay, color)
            
    def _draw_ripple(self, canvas, x, y, delay, color, max_r=60, step=0):
        if step > max_r:
            return
        alpha = 1.0 - (step / max_r)
        canvas.create_oval(
            x - step, y - step, x + step, y + step,
            outline=f"{color}{int(alpha*255):02x}",
            width=1,
            tags=f"ripple_{delay}"
        )
        self.root.after(
            10,
            lambda: self._draw_ripple(canvas, x, y, delay, color, max_r, step + 3)
        )
        # 清理旧涟漪
        if step > max_r - 3:
            canvas.after(200, lambda: canvas.delete(f"ripple_{delay}"))
            
    # ── 日志系统 ──
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        colors = {
            "INFO": CYBER_COLORS["neon_cyan"],
            "SUCCESS": CYBER_COLORS["success"],
            "WARNING": CYBER_COLORS["warning"],
            "ERROR": CYBER_COLORS["error"],
            "SYSTEM": CYBER_COLORS["neon_magenta"],
        }
        color = colors.get(level, CYBER_COLORS["text_secondary"])
        entry = f"[{timestamp}] [{level}] {message}"
        self.log_history.append((entry, color))
        
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{entry}\n")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")
        
        # 限制日志行数
        lines = self.log_text.get("1.0", "end-1c").split("\n")
        if len(lines) > 200:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "2.0")
            self.log_text.configure(state="disabled")
        
        self.status_label.configure(text=f"[ {level} ] {message[:60]}")
        
    # ── Toast通知 ──
    def _show_toast(self, message, duration=2000, color=CYBER_COLORS["neon_cyan"]):
        toast = ctk.CTkFrame(
            self.root, fg_color=CYBER_COLORS["bg_card"],
            corner_radius=10, border_width=1, border_color=color
        )
        lbl = ctk.CTkLabel(
            toast, text=message, font=("Microsoft YaHei UI", 13),
            text_color=color
        )
        lbl.pack(padx=16, pady=8)
        
        # 从顶部滑入
        toast.place(relx=0.5, rely=-0.1, anchor="n")
        self._slide_toast(toast, 0, 0.06, duration)
        
    def _slide_toast(self, toast, current, target, duration, step=0):
        if step > 20:
            self.root.after(duration, toast.destroy)
            return
        pos = current + (target - current) * (step / 10) if step <= 10 else target
        toast.place(relx=0.5, rely=pos, anchor="n")
        self.root.after(20, lambda: self._slide_toast(toast, pos, target, duration, step + 1))
        
    # ── 业务逻辑 ──
    def connect_share(self):
        # 立即给可见反馈：若点了按钮文字会变，说明点击已送达（用于排查“点了没反应”）
        try:
            self.btn_connect.configure(text="连接中…", state="disabled")
        except Exception:
            pass
        self.log("[连接] 正在建立连接...", "SYSTEM")
        share_path = self.share_entry.get()
        username = self.user_entry.get()
        password = self.pass_entry.get()
        
        # 记录连接操作
        log_operation("connect_share", {
            "share_path": share_path,
            "username": username,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        def _run():
            try:
                subprocess.run(
                    ["net", "use", share_path, "/delete", "/y"],
                    shell=False, capture_output=True, timeout=15,
                    creationflags=CREATE_NO_WINDOW
                )
                result = subprocess.run(
                    ["net", "use", share_path, password, f"/user:{username}", "/persistent:no"],
                    shell=False, capture_output=True, text=True, timeout=15,
                    creationflags=CREATE_NO_WINDOW
                )
                self.root.after(0, lambda: self._on_connect_result(result, share_path))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[连接] 异常: {str(e)}", "ERROR"))
                # 记录连接失败
                log_operation("connect_share_failed", {
                    "share_path": share_path,
                    "error": str(e),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, success=False)
        
        threading.Thread(target=_run, daemon=True).start()
        
    def _on_connect_result(self, result, share_path):
        try:
            self.btn_connect.configure(text="▸ 连接共享", state="normal")
        except Exception:
            pass
        if result.returncode == 0:
            self.log(f"[连接] ✓ 已连接: {share_path}", "SUCCESS")
            self.connection_indicator.configure(
                text="● 已连接", text_color=CYBER_COLORS["neon_green"]
            )
            self.stats_labels["conn"].configure(
                text="已连接", text_color=CYBER_COLORS["neon_green"]
            )
            self._show_toast("连接成功", 2000, CYBER_COLORS["neon_green"])
            self.refresh_file_list()
            # 记录连接成功
            log_operation("connect_share_success", {
                "share_path": share_path,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            self.log(f"[连接] ✗ 连接失败: {result.stderr.strip()}", "ERROR")
            self._show_toast("连接失败", 3000, CYBER_COLORS["neon_red"])
            # 记录连接失败
            log_operation("connect_share_failed", {
                "share_path": share_path,
                "error": result.stderr.strip(),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, success=False)
            
    def disconnect_share(self):
        share_path = self.share_entry.get()
        self.log(f"[断开] 正在断开: {share_path}", "SYSTEM")
        
        # 记录断开操作
        log_operation("disconnect_share", {
            "share_path": share_path,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        try:
            subprocess.run(["net", "use", share_path, "/delete", "/y"],
                         shell=False, capture_output=True, text=True,
                         creationflags=CREATE_NO_WINDOW)
            self.log("[断开] ✓ 已断开连接", "SUCCESS")
            self.connection_indicator.configure(
                text="● 未连接", text_color=CYBER_COLORS["text_dim"]
            )
            self.stats_labels["conn"].configure(
                text="未连接", text_color=CYBER_COLORS["text_dim"]
            )
            self._show_toast("已断开连接", 2000, CYBER_COLORS["neon_yellow"])
            self._clear_file_list()
            # 记录断开成功
            log_operation("disconnect_share_success", {
                "share_path": share_path,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            self.log(f"[断开] ✗ 出错: {str(e)}", "ERROR")
            # 记录断开失败
            log_operation("disconnect_share_failed", {
                "share_path": share_path,
                "error": str(e),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, success=False)
            
    def open_folder(self):
        share_path = self.share_entry.get()
        try:
            subprocess.run(["explorer", share_path], shell=False)
            self.log(f"[打开] 已打开资源管理器: {share_path}", "INFO")
            self._show_toast("已打开文件夹", 1500, CYBER_COLORS["neon_blue"])
        except Exception as e:
            self.log(f"[打开] 失败: {str(e)}", "ERROR")
            
    def test_connection(self):
        self.log("[测试] 正在检测网络连通性...", "SYSTEM")
        
        def _run():
            try:
                share_path = self.share_entry.get()
                host = share_path.split("\\")[2]
                result = subprocess.run(["ping", "-n", "2", host],
                                      capture_output=True, text=True, shell=False,
                                      creationflags=CREATE_NO_WINDOW)
                
                if result.returncode == 0:
                    self.root.after(0, lambda: self.log(f"[测试] ✓ 主机可达: {host}", "SUCCESS"))
                    self.root.after(0, lambda: self._show_toast(f"主机 {host} 可达", 2000, CYBER_COLORS["success"]))
                else:
                    self.root.after(0, lambda: self.log(f"[测试] ✗ 无法访问: {host}", "ERROR"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[测试] 异常: {str(e)}", "ERROR"))
                
        threading.Thread(target=_run, daemon=True).start()
        
    def refresh_file_list(self):
        share_path = self.share_entry.get()
        self.log("[刷新] 正在获取文件列表...", "INFO")
        self.path_label.configure(text=share_path[:80])
        
        def _run():
            try:
                if not os.path.exists(share_path):
                    self.root.after(0, lambda: self.log("[刷新] ✗ 路径不可访问", "ERROR"))
                    return
                
                files = []
                for item in os.listdir(share_path):
                    item_path = os.path.join(share_path, item)
                    try:
                        if os.path.isfile(item_path):
                            size = os.path.getsize(item_path)
                            mtime = datetime.fromtimestamp(os.path.getmtime(item_path))
                            files.append(("file", item, self._fmt_size(size), mtime.strftime("%Y-%m-%d %H:%M"), os.path.splitext(item)[1] or "无"))
                        else:
                            files.append(("folder", item, "--", "--", "文件夹"))
                    except Exception:
                        continue
                
                # 文件夹在前，按名排序
                files.sort(key=lambda x: (0 if x[0] == "folder" else 1, x[1].lower()))
                
                total_size = sum(
                    os.path.getsize(os.path.join(share_path, f[1]))
                    for f in files if f[0] == "file"
                )
                
                self.root.after(0, lambda: self._populate_file_list(files, total_size))
                self.root.after(0, lambda: self.log(f"[刷新] ✓ 找到 {len(files)} 个项目", "SUCCESS"))
                
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[刷新] ✗ {str(e)}", "ERROR"))
                
        threading.Thread(target=_run, daemon=True).start()
        
    def _populate_file_list(self, files, total_size):
        self._clear_file_list()

        if not files:
            empty = ctk.CTkLabel(
                self.file_scroll, text="📭  当前目录为空",
                font=("Microsoft YaHei UI", 14),
                text_color=CYBER_COLORS["text_dim"]
            )
            empty.pack(expand=True, pady=40)
            self.stats_labels["files"].configure(text="0")
            self.stats_labels["size"].configure(text="0 B")
            return

        for index, (ftype, name, size, mtime, ext) in enumerate(files):
            self._add_file_row(ftype, name, size, mtime, ext, index)

        self.stats_labels["files"].configure(text=str(len(files)))
        self.stats_labels["size"].configure(text=self._fmt_size(total_size))
        
    def _add_file_row(self, ftype, name, size, mtime, ext, index=0):
        color = CYBER_COLORS["neon_cyan"] if ftype == "folder" else CYBER_COLORS["text_primary"]
        icon = "📁" if ftype == "folder" else "📄"

        # 存储文件数据
        self._file_data[name] = (ftype, size, mtime, ext)

        # 隔行底色，提升长列表可读性
        base_bg = "#141430" if index % 2 else "transparent"
        row = ctk.CTkFrame(self.file_scroll, fg_color=base_bg, height=32)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)
        
        # 复选框
        var = ctk.BooleanVar(value=False)
        self._file_checkboxes[name] = var
        cb = ctk.CTkCheckBox(
            row, text="", variable=var, width=22,
            fg_color=CYBER_COLORS["neon_cyan"], hover_color=CYBER_COLORS["neon_cyan"],
            border_color=CYBER_COLORS["text_dim"], border_width=1,
            command=self._on_check_toggle
        )
        cb.pack(side="left", padx=(4, 0))
        
        # 文件名
        name_frame = ctk.CTkFrame(row, fg_color="transparent", width=300)
        name_frame.pack(side="left", padx=(4, 0))
        name_frame.pack_propagate(False)
        lbl = ctk.CTkLabel(
            name_frame, text=f"  {icon}  {name}", font=("Cascadia Code", 11),
            text_color=color, anchor="w"
        )
        lbl.pack(fill="both", expand=True)
        
        # 大小
        ctk.CTkLabel(
            row, text=size, font=("Cascadia Code", 10),
            text_color=CYBER_COLORS["text_secondary"], width=90
        ).pack(side="left", padx=(0, 4))
        
        # 时间
        ctk.CTkLabel(
            row, text=mtime, font=("Cascadia Code", 10),
            text_color=CYBER_COLORS["text_secondary"], width=130
        ).pack(side="left", padx=(0, 4))
        
        # 类型
        ctk.CTkLabel(
            row, text=ext, font=("Cascadia Code", 9),
            text_color=CYBER_COLORS["text_dim"], width=70
        ).pack(side="left")
        
        # 悬停高亮
        def on_enter(e, r=row):
            r.configure(fg_color="#1a1a3a")
        def on_leave(e, r=row):
            r.configure(fg_color="transparent")
        
        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)
        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        cb.bind("<Enter>", on_enter)
        cb.bind("<Leave>", on_leave)
        
        # 右键菜单（仅文件，不含文件夹）
        if ftype == "file":
            row.bind("<Button-3>", lambda e, n=name: self._show_context_menu(e, n))
            lbl.bind("<Button-3>", lambda e, n=name: self._show_context_menu(e, n))
        
        # 左键单击：预览（PDF/图片）；双击：用系统程序打开
        if ftype == "folder":
            row.bind("<Button-1>", lambda e, n=name: self._enter_folder(n))
        else:
            row.bind("<Button-1>", lambda e, n=name: self._preview_file(n))
            lbl.bind("<Double-1>", lambda e, n=name: self._open_file(n))
            
    def _clear_file_list(self):
        for widget in self.file_scroll.winfo_children():
            widget.destroy()
        self._file_checkboxes.clear()
        self._file_data.clear()
        self.select_all_var.set(False)
            
    def _enter_folder(self, folder_name):
        current = self.share_entry.get()
        new_path = os.path.join(current, folder_name)
        self.share_entry.delete(0, "end")
        self.share_entry.insert(0, new_path)
        self.log(f"[导航] 进入: {folder_name}", "INFO")
        self.refresh_file_list()

    def _go_up(self):
        """返回上一级目录"""
        current = self.share_entry.get().rstrip("/\\")
        parent = os.path.dirname(current)
        if parent and parent != current and not parent.endswith(":"):
            self.share_entry.delete(0, "end")
            self.share_entry.insert(0, parent)
            self.log(f"[导航] 返回上级: {parent}", "INFO")
            self.refresh_file_list()
        else:
            self.log("[导航] 已是最顶层", "INFO")
        
    def _open_file(self, file_name):
        share_path = self.share_entry.get()
        file_path = os.path.join(share_path, file_name)
        try:
            os.startfile(file_path)
            self.log(f"[打开] 文件: {file_name}", "INFO")
            self._show_toast(f"已打开: {file_name}", 1500, CYBER_COLORS["neon_blue"])
        except Exception as e:
            self.log(f"[打开] 失败: {str(e)}", "ERROR")

    # ── 文件预览 ──
    def _preview_file(self, file_name):
        """单击文件行时触发：根据类型渲染预览（图片/PDF），其它类型显示提示"""
        data = self._file_data.get(file_name)
        if not data:
            return
        ftype, size, mtime, ext = data
        if ftype == "folder":
            return
        share_path = self.share_entry.get()
        file_path = os.path.join(share_path, file_name)
        self._preview_path = file_path
        if getattr(self, "preview_open_btn", None) is not None:
            self.preview_open_btn.configure(state="normal")
        self.preview_name.configure(text=file_name)
        self.preview_meta.configure(
            text=f"类型: {ext or '未知'}    大小: {size}    修改: {mtime}"
        )
        ext_lower = (ext or "").lower()
        if ext_lower in IMAGE_EXTS:
            self._preview_mode = "loading"
            self._preview_loading_text = "🖼  正在加载图片…"
            self._render_preview()
            threading.Thread(target=self._load_image_preview, args=(file_path,), daemon=True).start()
        elif ext_lower in PDF_EXTS:
            self._preview_mode = "loading"
            self._preview_loading_text = "📄  正在渲染 PDF 首页…"
            self._render_preview()
            threading.Thread(target=self._load_pdf_preview, args=(file_path,), daemon=True).start()
        else:
            self._preview_mode = "info"
            self._preview_pil = None
            self._render_preview()

    def _load_image_preview(self, path):
        try:
            self._preview_pil = Image.open(path).convert("RGB")
            self._preview_mode = "image"
            self.root.after(0, self._render_preview)
        except Exception as e:
            self._preview_mode = "info"
            self._preview_pil = None
            self.root.after(0, self._render_preview)
            self.root.after(0, lambda: self.log(f"[预览] 图片加载失败: {e}", "ERROR"))

    def _load_pdf_preview(self, path):
        try:
            import fitz
            doc = fitz.open(path)
            page = doc[0]
            mat = fitz.Matrix(1.6, 1.6)
            pix = page.get_pixmap(matrix=mat)
            self._preview_pil = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            doc.close()
            self._preview_mode = "image"
            self.root.after(0, self._render_preview)
        except ImportError:
            # fitz（PyMuPDF）未打包进 exe —— 不影响程序启动，仅 PDF 预览不可用
            self._preview_mode = "info"
            self._preview_pil = None
            self._preview_loading_text = ""
            self.root.after(0, self._render_preview)
            self.root.after(0, lambda: self._show_pdf_unavailable())
        except Exception as e:
            self._preview_mode = "info"
            self._preview_pil = None
            self.root.after(0, self._render_preview)
            self.root.after(0, lambda: self.log(
                f"[预览] PDF 渲染失败: {e}", "ERROR"))

    def _show_pdf_unavailable(self):
        """PDF 预览组件未包含时的友好提示（仅信息，不阻塞）"""
        try:
            messagebox.showinfo(
                "PDF 预览未启用",
                "当前版本未打包 PyMuPDF，无法在程序内预览 PDF 首页。\n\n"
                "你可以：\n"
                "• 用右侧「↗ 打开」按钮调用系统/默认程序查看；\n"
                "• 或联系开发者在打包时加入 PyMuPDF 以启用内嵌预览。",
                parent=self.root
            )
        except Exception:
            pass

    def _render_preview(self):
        """根据当前 _preview_mode 重建预览区内容（图片会按面板尺寸自适应缩放）"""
        for w in self.preview_scroll.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        if self._preview_mode == "none":
            ctk.CTkLabel(
                self.preview_scroll, text="👁\n\n单击左侧文件\n查看预览",
                font=("Microsoft YaHei UI", 14), text_color=CYBER_COLORS["text_dim"],
                justify="center"
            ).pack(expand=True, fill="both", pady=40)
        elif self._preview_mode == "loading":
            ctk.CTkLabel(
                self.preview_scroll, text=self._preview_loading_text,
                font=("Microsoft YaHei UI", 13), text_color=CYBER_COLORS["text_secondary"]
            ).pack(expand=True, pady=40)
        elif self._preview_mode == "info":
            frame = ctk.CTkFrame(self.preview_scroll, fg_color="transparent")
            frame.pack(expand=True, fill="both", pady=30)
            ctk.CTkLabel(
                frame, text="📦", font=("Segoe UI Symbol", 48),
                text_color=CYBER_COLORS["neon_blue"]
            ).pack(pady=(0, 10))
            ctk.CTkLabel(
                frame, text="该文件类型暂不支持预览\n可用「打开」按钮调用系统程序",
                font=("Microsoft YaHei UI", 13), text_color=CYBER_COLORS["text_secondary"],
                justify="center"
            ).pack()
        elif self._preview_mode == "image" and self._preview_pil is not None:
            try:
                avail_w = max(50, self.preview_scroll.winfo_width() - 20)
                avail_h = max(50, self.preview_scroll.winfo_height() - 20)
            except Exception:
                return
            w, h = self._preview_pil.size
            scale = min(avail_w / w, avail_h / h, 2.0)
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            resized = self._preview_pil.resize((nw, nh), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(nw, nh))
            self._preview_image = ctk_img
            ctk.CTkLabel(self.preview_scroll, image=ctk_img, text="").pack(expand=True, pady=10)

    def _open_previewed_file(self):
        if getattr(self, "_preview_path", None) and os.path.exists(self._preview_path):
            try:
                os.startfile(self._preview_path)
                self.log(f"[打开] {os.path.basename(self._preview_path)}", "INFO")
            except Exception as e:
                self.log(f"[打开] 失败: {e}", "ERROR")

    def _on_drag_drop_upload(self, event):
        """处理拖拽上传"""
        files = event.data.strip('{}').split('} {')
        for file_path in files:
            if not file_path:
                continue
            file_path = file_path.strip()
            if os.path.isfile(file_path):
                self._upload_dragged_file(file_path)
            elif os.path.isdir(file_path):
                self.log(f"[拖拽] 暂不支持文件夹上传: {os.path.basename(file_path)}", "WARNING")
                self._show_toast("暂不支持文件夹上传", 2000, CYBER_COLORS["neon_yellow"])
    
    def _upload_dragged_file(self, file_path):
        """上传拖拽的文件"""
        share_path = self.share_entry.get()
        file_name = os.path.basename(file_path)
        dest = os.path.join(share_path, file_name)
        
        self.log(f"[拖拽上传] 正在上传: {file_name}", "INFO")
        self._show_toast(f"正在上传: {file_name}", 1500, CYBER_COLORS["neon_cyan"])
        
        # 记录上传操作
        log_operation("drag_upload_file", {
            "local_path": file_path,
            "file_name": file_name,
            "dest_path": dest,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        def _run():
            try:
                shutil.copy2(file_path, dest)
                self.root.after(0, lambda: self.log(f"[拖拽上传] ✓ 成功: {file_name}", "SUCCESS"))
                self.root.after(0, lambda: self._show_toast(f"上传成功: {file_name}", 2000, CYBER_COLORS["success"]))
                self.root.after(0, self.refresh_file_list)
                # 记录上传成功
                log_operation("drag_upload_file_success", {
                    "file_name": file_name,
                    "dest_path": dest,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[拖拽上传] ✗ {str(e)}", "ERROR"))
                self.root.after(0, lambda: self._show_toast(f"上传失败: {file_name}", 3000, CYBER_COLORS["neon_red"]))
                # 记录上传失败
                log_operation("drag_upload_file_failed", {
                    "file_name": file_name,
                    "error": str(e),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, success=False)
        
        threading.Thread(target=_run, daemon=True).start()
            
    def upload_file(self):
        file_path = filedialog.askopenfilename(title="选择要上传的文件")
        if not file_path:
            return
            
        share_path = self.share_entry.get()
        file_name = os.path.basename(file_path)
        dest = os.path.join(share_path, file_name)
        
        self.log(f"[上传] 正在上传: {file_name}", "INFO")
        
        # 记录上传操作
        log_operation("upload_file", {
            "local_path": file_path,
            "file_name": file_name,
            "dest_path": dest,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        def _run():
            try:
                shutil.copy2(file_path, dest)
                self.root.after(0, lambda: self.log(f"[上传] ✓ 成功: {file_name}", "SUCCESS"))
                self.root.after(0, lambda: self._show_toast(f"上传成功: {file_name}", 2000, CYBER_COLORS["success"]))
                self.root.after(0, self.refresh_file_list)
                # 记录上传成功
                log_operation("upload_file_success", {
                    "file_name": file_name,
                    "dest_path": dest,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[上传] ✗ {str(e)}", "ERROR"))
                # 记录上传失败
                log_operation("upload_file_failed", {
                    "file_name": file_name,
                    "error": str(e),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, success=False)
                
        threading.Thread(target=_run, daemon=True).start()
        
    def download_file(self):
        """从共享下载文件：先选择源文件，再选择本地保存位置（修复原逻辑倒置 bug）"""
        share_path = self.share_entry.get()
        if not os.path.exists(share_path):
            self.log("[下载] ✗ 共享不可访问，请先连接", "ERROR")
            self._show_toast("请先连接共享", 2000, CYBER_COLORS["neon_red"])
            return

        source = filedialog.askopenfilename(
            title="选择要下载的文件",
            initialdir=share_path
        )
        if not source:
            return

        file_name = os.path.basename(source)
        dest = filedialog.asksaveasfilename(
            title=f"保存文件 - {file_name}",
            initialfile=file_name
        )
        if not dest:
            return

        self.log(f"[下载] 正在下载: {file_name}", "INFO")

        # 记录下载操作
        log_operation("download_file", {
            "source_path": source,
            "file_name": file_name,
            "dest_path": dest,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        def _run():
            try:
                shutil.copy2(source, dest)
                self.root.after(0, lambda: self.log(f"[下载] ✓ 成功: {file_name}", "SUCCESS"))
                self.root.after(0, lambda: self._show_toast(f"下载成功: {file_name}", 2000, CYBER_COLORS["success"]))
                # 记录下载成功
                log_operation("download_file_success", {
                    "file_name": file_name,
                    "dest_path": dest,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[下载] ✗ {str(e)}", "ERROR"))
                # 记录下载失败
                log_operation("download_file_failed", {
                    "file_name": file_name,
                    "error": str(e),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, success=False)

        threading.Thread(target=_run, daemon=True).start()
        
    def delete_file(self):
        share_path = self.share_entry.get()
        file_path = filedialog.askopenfilename(
            title="选择要删除的文件",
            initialdir=share_path
        ) if os.path.exists(share_path) else filedialog.askopenfilename(title="选择要删除的文件")
        
        if not file_path:
            return
            
        file_name = os.path.basename(file_path)
        
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除 '{file_name}' 吗？\n此操作不可恢复。",
            parent=self.root
        )
        if not confirm:
            return
            
        self.log(f"[删除] 正在删除: {file_name}", "WARNING")
        
        # 记录删除操作
        log_operation("delete_file", {
            "file_path": file_path,
            "file_name": file_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
            else:
                shutil.rmtree(file_path)
            self.log(f"[删除] ✓ 已删除: {file_name}", "SUCCESS")
            self._show_toast(f"已删除: {file_name}", 2000, CYBER_COLORS["warning"])
            self.refresh_file_list()
            # 记录删除成功
            log_operation("delete_file_success", {
                "file_name": file_name,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            self.log(f"[删除] ✗ {str(e)}", "ERROR")
            # 记录删除失败
            log_operation("delete_file_failed", {
                "file_name": file_name,
                "error": str(e),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, success=False)
            
    # ── 工具方法 ──
    @staticmethod
    def _fmt_size(size_bytes):
        if size_bytes == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
        
    def _show_about(self):
        """关于窗口"""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("关于 SCAN.GATE")
        dialog.geometry("550x520")
        dialog.resizable(False, False)
        dialog.configure(fg_color=CYBER_COLORS["bg_primary"])
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.lift()           # 置顶，避免被主窗口挡住而“看不见”
        dialog.focus_force()
        
        # 居中并限定在主窗口范围内：位置随主窗口大小自适应，按钮始终在窗口内
        self.root.update_idletasks()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        x = max(rx, min(rx + (rw - 550) // 2, rx + rw - 550))
        y = max(ry, min(ry + (rh - 520) // 2, ry + rh - 520))
        dialog.geometry(f"+{x}+{y}")
        
        main = ctk.CTkFrame(dialog, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=24)
        
        # 顶部标题
        ctk.CTkLabel(
            main, text="◈", font=("Segoe UI Symbol", 40),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack(pady=(8, 4))
        
        ctk.CTkLabel(
            main, text="SCAN.GATE", font=("Cascadia Code", 28, "bold"),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack()
        
        ctk.CTkLabel(
            main, text="打印机扫描终端 v2.0", font=("Cascadia Code", 14),
            text_color=CYBER_COLORS["text_secondary"]
        ).pack(pady=(2, 20))
        
        # 版权归属
        copyright_frame = ctk.CTkFrame(
            main, fg_color=CYBER_COLORS["bg_card"], corner_radius=10
        )
        copyright_frame.pack(fill="x", pady=(0, 16))
        
        ctk.CTkLabel(
            copyright_frame, text="© 版权所有", font=("Microsoft YaHei UI", 15, "bold"),
            text_color=CYBER_COLORS["neon_magenta"]
        ).pack(pady=(16, 6))
        
        name_label = ctk.CTkLabel(
            copyright_frame, text="刘思元", font=("Microsoft YaHei UI", 24, "bold"),
            text_color=CYBER_COLORS["text_primary"], cursor="hand2"
        )
        name_label.pack()
        name_label.bind("<Button-1>", lambda e: self._show_contact_choice())
        
        ctk.CTkLabel(
            copyright_frame, text="All Rights Reserved", font=("Cascadia Code", 11),
            text_color=CYBER_COLORS["text_dim"]
        ).pack(pady=(4, 16))
        
        # 使用说明
        guide_frame = ctk.CTkFrame(
            main, fg_color=CYBER_COLORS["bg_card"], corner_radius=10
        )
        guide_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            guide_frame, text="📖 使用说明", font=("Microsoft YaHei UI", 15, "bold"),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack(anchor="w", padx=20, pady=(16, 10))
        
        instructions = [
            ("1. 连接共享", "输入打印机共享路径及凭据，点击「连接共享」按钮挂载网络共享文件夹"),
            ("2. 浏览文件", "连接成功后，右侧面板自动显示共享目录中的所有 PDF 文件"),
            ("3. 上传文件", "点击「上传文件」选择本地文件，上传到共享目录中"),
            ("4. 下载文件", "选中文件后点击「下载文件」，将远程文件保存到本地"),
            ("5. 删除文件", "选中远程文件后点击「删除文件」将其移除，操作不可恢复"),
            ("6. 断开连接", "使用完毕后点击「断开连接」卸载网络共享"),
        ]
        
        for title_text, desc in instructions:
            row = ctk.CTkFrame(guide_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(
                row, text=title_text, font=("Microsoft YaHei UI", 12, "bold"),
                text_color=CYBER_COLORS["neon_green"], width=100, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=desc, font=("Microsoft YaHei UI", 11),
                text_color=CYBER_COLORS["text_secondary"], anchor="w"
            ).pack(side="left", padx=(8, 0))
        
        # 关闭按钮
        NeonButton(
            main, text="关闭", neon_color=CYBER_COLORS["neon_cyan"],
            command=dialog.destroy
        ).pack(pady=(16, 0))
    
    # ── 文件选择功能 ──
    def _on_check_toggle(self):
        """当复选框状态变化时更新全选状态"""
        if not self._file_checkboxes:
            return
        all_checked = all(var.get() for var in self._file_checkboxes.values())
        self.select_all_var.set(all_checked)
    
    def _toggle_select_all(self):
        """全选/取消全选所有文件"""
        state = self.select_all_var.get()
        for var in self._file_checkboxes.values():
            var.set(state)
    
    def _delete_selected_files(self):
        """删除选中的文件"""
        selected = [name for name, var in self._file_checkboxes.items() 
                   if var.get() and self._file_data.get(name, ("",))[0] == "file"]
        
        if not selected:
            self.log("[删除] 未选中任何文件", "WARNING")
            self._show_toast("请先勾选要删除的文件", 2000, CYBER_COLORS["neon_yellow"])
            return
        
        confirm = messagebox.askyesno(
            "确认批量删除",
            f"确定要删除 {len(selected)} 个文件吗？\n此操作不可恢复。\n\n文件列表：\n" + "\n".join(selected[:10]) + 
            ("\n..." if len(selected) > 10 else ""),
            parent=self.root
        )
        if not confirm:
            return
        
        share_path = self.share_entry.get()
        success_count = 0
        fail_count = 0
        
        for file_name in selected:
            file_path = os.path.join(share_path, file_name)
            try:
                os.remove(file_path)
                success_count += 1
                self.log(f"[批量删除] ✓ {file_name}", "SUCCESS")
                # 记录删除操作
                log_operation("batch_delete_file", {
                    "file_name": file_name,
                    "file_path": file_path,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, success=True)
            except Exception as e:
                fail_count += 1
                self.log(f"[批量删除] ✗ {file_name}: {str(e)}", "ERROR")
                # 记录删除失败
                log_operation("batch_delete_file", {
                    "file_name": file_name,
                    "error": str(e),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, success=False)
        
        if success_count > 0:
            self._show_toast(f"已删除 {success_count} 个文件", 2000, CYBER_COLORS["success"])
            self.refresh_file_list()
        if fail_count > 0:
            self._show_toast(f"{fail_count} 个文件删除失败", 3000, CYBER_COLORS["neon_red"])
    
    def _show_context_menu(self, event, file_name):
        """显示右键菜单"""
        menu = Menu(self.root, tearoff=0, 
                   bg=CYBER_COLORS["bg_card"],
                   fg=CYBER_COLORS["text_primary"],
                   activebackground=CYBER_COLORS["bg_input"],
                   activeforeground=CYBER_COLORS["neon_cyan"])
        
        menu.add_command(label="下载到指定路径", 
                        command=lambda: self._download_single_file(file_name))
        menu.add_separator()
        menu.add_command(label="删除此文件", 
                        command=lambda: self._delete_single_file(file_name))
        
        # 显示菜单
        menu.tk_popup(event.x_root, event.y_root)
    
    def _download_single_file(self, file_name):
        """下载单个文件到指定路径"""
        share_path = self.share_entry.get()
        source = os.path.join(share_path, file_name)
        
        dest = filedialog.asksaveasfilename(
            title=f"保存文件 - {file_name}",
            initialfile=file_name
        )
        if not dest:
            return
        
        self.log(f"[下载] 正在下载: {file_name}", "INFO")
        
        # 记录下载操作
        log_operation("context_download_file", {
            "source_path": source,
            "file_name": file_name,
            "dest_path": dest,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        def _run():
            try:
                shutil.copy2(source, dest)
                self.root.after(0, lambda: self.log(f"[下载] ✓ 成功: {file_name}", "SUCCESS"))
                self.root.after(0, lambda: self._show_toast(f"下载成功: {file_name}", 2000, CYBER_COLORS["success"]))
                # 记录下载成功
                log_operation("context_download_file_success", {
                    "file_name": file_name,
                    "dest_path": dest,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as e:
                self.root.after(0, lambda: self.log(f"[下载] ✗ {str(e)}", "ERROR"))
                # 记录下载失败
                log_operation("context_download_file_failed", {
                    "file_name": file_name,
                    "error": str(e),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }, success=False)
        
        threading.Thread(target=_run, daemon=True).start()
    
    def _delete_single_file(self, file_name):
        """删除单个文件"""
        share_path = self.share_entry.get()
        file_path = os.path.join(share_path, file_name)
        
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除 '{file_name}' 吗？\n此操作不可恢复。",
            parent=self.root
        )
        if not confirm:
            return
        
        self.log(f"[右键删除] 正在删除: {file_name}", "WARNING")
        
        # 记录删除操作
        log_operation("context_delete_file", {
            "file_path": file_path,
            "file_name": file_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        try:
            os.remove(file_path)
            self.log(f"[右键删除] ✓ 已删除: {file_name}", "SUCCESS")
            self._show_toast(f"已删除: {file_name}", 2000, CYBER_COLORS["warning"])
            self.refresh_file_list()
            # 记录删除成功
            log_operation("context_delete_file_success", {
                "file_name": file_name,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            self.log(f"[右键删除] ✗ {str(e)}", "ERROR")
            # 记录删除失败
            log_operation("context_delete_file_failed", {
                "file_name": file_name,
                "error": str(e),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, success=False)
    
    def _show_contact_choice(self):
        """点击署名弹窗：选择公司内 / 公司外，打开对应飞书加友链接"""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("添加联系方式")
        dialog.geometry("420x300")
        dialog.resizable(False, False)
        dialog.configure(fg_color=CYBER_COLORS["bg_primary"])
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")

        main = ctk.CTkFrame(dialog, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(
            main, text="◈ 选择联系方式", font=("Microsoft YaHei UI", 18, "bold"),
            text_color=CYBER_COLORS["neon_cyan"]
        ).pack(pady=(4, 6))

        ctk.CTkLabel(
            main, text="请选择您当前所在的网络环境", font=("Microsoft YaHei UI", 13),
            text_color=CYBER_COLORS["text_secondary"]
        ).pack(pady=(0, 22))

        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 8))

        def _pick(internal):
            dialog.destroy()
            self._open_feishu_link(internal=internal)

        NeonButton(
            btn_frame, text="🏢 公司内", neon_color=CYBER_COLORS["neon_green"],
            command=lambda: _pick(True)
        ).pack(fill="x", pady=(0, 12))

        NeonButton(
            btn_frame, text="🌐 公司外", neon_color=CYBER_COLORS["neon_blue"],
            command=lambda: _pick(False)
        ).pack(fill="x")

    def _open_feishu_link(self, internal=False):
        """打开飞书加友链接；internal=True 走公司内专用链接，否则用公司外原链接"""
        if internal:
            url = "https://www.feishu.cn/invitation/page/add_contact/?token=9danc903-e18d-4e65-a6db-84f298eee4bf&unique_id=kwPuzpyzgwlmgKzs_R4Yrw=="
        else:
            url = "https://www.feishu.cn/invitation/page/add_contact/?token=499l9235-d879-4aae-8998-705ab4102695"
        try:
            import webbrowser
            webbrowser.open(url)
            self.log(f"[飞书] 已打开链接: {url}", "INFO")
        except Exception as e:
            self.log(f"[飞书] 打开链接失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"无法打开链接: {str(e)}")
    
    def run(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
        self.root.mainloop()


# ── 入口 ──
if __name__ == "__main__":
    if _is_already_running():
        _show_already_running()
        sys.exit(0)
    app = CyberPrinterApp()
    app.run()