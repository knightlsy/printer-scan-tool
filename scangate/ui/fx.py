"""视觉工具与苹果风控件（精致版）。"""

import random
import time
import customtkinter as ctk
import ctypes
from PIL import Image, ImageDraw, ImageFilter, ImageChops

from scangate.ui.theme import (
    FONT, BTN_RADIUS, DUR_HOVER, DUR_PRESS, DUR_FOCUS, LIFT_PX, PRESS_SCALE,
    SHADOW_BLUR, SHADOW_ALPHA, SHADOW_OFFSET,
    BG_TOP, BG_MID, BG_BOT,
)


# ---------------- 颜色工具 ----------------
def _hex_to_rgb(c: str):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))


def _clamp(v: int) -> int:
    return max(0, min(255, v))


def is_hex(c) -> bool:
    return isinstance(c, str) and c.startswith("#") and len(c) in (4, 7)


def lerp_color(a: str, b: str, t: float) -> str:
    """在两种颜色之间线性插值（t∈[0,1]），返回 #rrggbb。"""
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    r = _clamp(int(ar + (br - ar) * t))
    g = _clamp(int(ag + (bg - ag) * t))
    b = _clamp(int(ab + (bb - ab) * t))
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighter(c: str, t: float) -> str:
    if not is_hex(c):
        return c
    return lerp_color(c, "#ffffff", t)


def _darker(c: str, t: float) -> str:
    if not is_hex(c):
        return c
    return lerp_color(c, "#000000", t)


def safe_configure(widget, **kw):
    """销毁安全的 configure。"""
    try:
        if widget.winfo_exists():
            widget.configure(**kw)
    except Exception:
        pass


# ---------------- 补间动画引擎 ----------------
def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def animate(widget, duration_ms: int, on_step, easing=ease_out_cubic, on_done=None):
    """在 duration_ms 内以 easing 调用 on_step(eased_t)；每帧 ~16ms。"""
    root = widget.winfo_toplevel()
    t0 = [None]

    def tick():
        if not widget.winfo_exists():
            return
        if t0[0] is None:
            t0[0] = time.monotonic()
        el = (time.monotonic() - t0[0]) * 1000
        t = 1.0 if duration_ms <= 0 else min(1.0, el / duration_ms)
        try:
            on_step(easing(t), t)
        except Exception:
            pass
        if t < 1:
            root.after(16, tick)
        elif on_done is not None:
            try:
                on_done()
            except Exception:
                pass

    if widget.winfo_exists():
        root.after(16, tick)


def round_window(hwnd: int) -> None:
    """为无边框窗口添加系统级圆角（Windows 11 DWM）。"""
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(ctypes.c_int(DWMWCP_ROUND)),
            ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass


# ---------------- 图像辅助 ----------------
def _rounded_mask(w, h, radius):
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return m


def _dither(img, amp=2):
    """给图像叠加细微随机噪声，打破 8-bit 渐变断层（不影响 alpha 通道）。

    采用小噪声块平铺（避免逐像素 Python 循环），幅度极低（默认 ±2），
    足够消除色阶断层又不会引入可见颗粒感。噪声为加性，背景整体偏亮，
    极小的亮度偏移人眼不可辨。
    """
    if img.mode not in ("RGB", "RGBA"):
        return img
    w, h = img.size
    tw, th = 128, 128
    tile = Image.new("L", (tw, th))
    tile.putdata([random.randint(0, 2 * amp) for _ in range(tw * th)])
    full = Image.new("L", (w, h))
    for y in range(0, h, th):
        for x in range(0, w, tw):
            full.paste(tile, (x, y))
    if img.mode == "RGB":
        return ImageChops.add(img, full.convert("RGB"))
    r, g, b, a = img.split()
    rgb = ImageChops.add(Image.merge("RGB", (r, g, b)), full.convert("RGB"))
    return Image.merge("RGBA", (*rgb.split(), a))


def _vgrad_rgba(w, h, top, bottom):
    g = Image.new("RGBA", (1, h), top)
    px = g.load()
    tr, tg, tb, ta = top
    br, bg, bb, ba = bottom
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = (
            int(tr + (br - tr) * t), int(tg + (bg - tg) * t),
            int(tb + (bb - tb) * t), int(ta + (ba - ta) * t),
        )
    fill = g.resize((w, h))
    # 玻璃表面渐变同样需要抖动，否则上亮下暗的细微过渡会出现色阶
    return _dither(fill, amp=2)


# ---------------- 毛玻璃 / 阴影 图像生成 ----------------
def make_glass_image(width, height, radius=22, *, alpha=0.72, tint="#ffffff",
                     border="#c9c9d1", border_width=1.5, highlight="#ffffff",
                     highlight_alpha=70, grad=True):
    """生成半透明渐变磨砂玻璃表面（RGBA）：上亮下微暗渐变 + 描边 + 顶部高光。"""
    w = max(2, int(round(width)))
    h = max(2, int(round(height)))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tr, tg, tb = _hex_to_rgb(tint)
    ta = int(255 * alpha)
    ba = max(0, ta - 12)
    fill_top = (tr, tg, tb, ta)
    fill_bot = (_clamp(int(tr * 0.97)), _clamp(int(tg * 0.97)),
                _clamp(int(tb * 0.97)), ba)
    fill = _vgrad_rgba(w, h, fill_top, fill_bot) if grad else Image.new("RGBA", (w, h), fill_top)
    mask = _rounded_mask(w, h, radius)
    img.paste(fill, (0, 0), mask)

    if border_width and border_width > 0:
        br, bg, bb = _hex_to_rgb(border)
        bw = max(1, int(round(border_width)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [bw / 2, bw / 2, w - 1 - bw / 2, h - 1 - bw / 2],
            radius=max(1, radius - bw / 2),
            outline=(br, bg, bb, 235), width=bw,
        )
    hr, hg, hb = _hex_to_rgb(highlight)
    d = ImageDraw.Draw(img)
    d.line([radius, 1, w - radius - 1, 1], fill=(hr, hg, hb, highlight_alpha), width=1)
    return img


def make_shadow_image(width, height, radius=22, *, blur=26, alpha=0.18, offset=10):
    """生成一张柔和投影（RGBA，黑色高斯模糊）。"""
    w = max(2, int(round(width)))
    h = max(2, int(round(height)))
    pad = blur * 2 + max(1, offset)
    big = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle(
        [pad, pad + offset, pad + w - 1, pad + h - 1 + offset],
        radius=radius, fill=(0, 0, 0, 255),
    )
    big = big.filter(ImageFilter.GaussianBlur(blur))
    a = big.split()[3].point(lambda v: int(v * alpha))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out.putalpha(a)
    return out


# ---------------- 背景（多段渐变 + 顶部高光） ----------------
def make_background(width, height):
    """柔和竖向多段渐变 + 顶部光源高光（RGB），朦胧底图。

    颜色统一取自 theme 的冷蓝灰（BG_TOP/MID/BOT），与面板、按钮同色系；
    模糊后再叠加细微抖动，彻底消除 8-bit 渐变断层。
    """
    w = max(2, int(round(width)))
    h = max(2, int(round(height)))
    top = _hex_to_rgb(BG_TOP)
    mid = _hex_to_rgb(BG_MID)
    bot = _hex_to_rgb(BG_BOT)

    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        if t < 0.5:
            a = t / 0.5
            c = tuple(int(top[i] + (mid[i] - top[i]) * a) for i in range(3))
        else:
            a = (t - 0.5) / 0.5
            c = tuple(int(mid[i] + (bot[i] - mid[i]) * a) for i in range(3))
        px[0, y] = c
    base = base.resize((w, h))

    glow = Image.new("RGBA", (1, h), (255, 255, 255, 0))
    gpx = glow.load()
    for y in range(h):
        t = y / max(1, h - 1)
        alpha = int(150 * max(0.0, 1.0 - t / 0.45))
        gpx[0, y] = (255, 255, 255, alpha)
    glow = glow.resize((w, h)).convert("RGB")
    base = Image.blend(base, glow, 0.5)
    base = base.filter(ImageFilter.GaussianBlur(50))
    # 模糊后再抖动：最终呈现的 8-bit 图像不再有可见色阶断层
    return _dither(base, amp=3)


# ---------------- 苹果风按钮（抬升 + 微缩 + 颜色补间 + 聚焦环） ----------------
class AppleButton(ctk.CTkFrame):
    """Apple Design Language 按钮（包裹式）。

    交互（全部 200–300ms 补间）：悬停抬升 + 投影浮现 + 颜色补间；
    按下微缩 + 颜色压暗；聚焦时外层圆角描边亮起（无障碍焦点）。
    变换通过 place 相对坐标完成，不影响兄弟控件布局（无抖动）。
    """

    def __init__(self, master, text: str = "", command=None, kind: str = "primary", **kw):
        width = int(kw.pop("width", 200))
        height = int(kw.pop("height", 40))
        super().__init__(master, fg_color="transparent", width=width, height=height)
        self._bw, self._bh = width, height
        self._cmd = command
        self._gen = 0

        style = self._make_style(kind)
        self._base = style["fg_color"]
        self._hover = style["hover_color"]
        self._press = _darker(self._base, 0.12) if is_hex(self._base) else self._hover
        self._txt = style["text_color"]
        self._manage_color = is_hex(self._base)
        self._cur_color = self._base

        self._shadow_img = None
        self._shadow = ctk.CTkLabel(self, text="", fg_color="transparent")
        self._shadow.place(relx=0.5, rely=0.5, anchor="center",
                           relwidth=1.0, relheight=1.0)

        self._btn = ctk.CTkButton(
            self, text=text, command=command,
            fg_color=self._base,
            hover_color=(self._hover if not self._manage_color else self._base),
            text_color=self._txt, corner_radius=BTN_RADIUS,
            border_width=0,
            width=width, height=height, font=FONT["body"],
        )
        self._btn.place(relx=0.5, rely=0.5, anchor="center",
                        relwidth=1.0, relheight=1.0)
        self._btn.tkraise()

        self._btn.bind("<Enter>", self._on_enter)
        self._btn.bind("<Leave>", self._on_leave)
        self._btn.bind("<Button-1>", self._on_press)
        self._btn.bind("<ButtonRelease-1>", self._on_release)
        self._btn.bind("<FocusIn>", self._on_focus_in)
        self._btn.bind("<FocusOut>", self._on_focus_out)

    @staticmethod
    def _make_style(kind: str) -> dict:
        from scangate.ui.theme import (
            ACCENT, ACCENT_HI, ACCENT_PRESS, ACCENT_SOFT,
            DANGER, DANGER_HI, DANGER_PRESS,
            GRAY_BTN, GRAY_BTN_HI, GRAY_BTN_PRESS, TEXT,
        )
        if kind == "primary":
            return dict(fg_color=ACCENT, hover_color=ACCENT_HI, text_color="#ffffff")
        if kind == "danger":
            return dict(fg_color=DANGER, hover_color=DANGER_HI, text_color="#ffffff")
        if kind == "ghost":
            return dict(fg_color="transparent", hover_color=ACCENT_SOFT, text_color=ACCENT)
        return dict(fg_color=GRAY_BTN, hover_color=GRAY_BTN_HI, text_color=TEXT)

    def _anim(self, dur, fn, on_done=None, easing=ease_out_cubic):
        self._gen += 1
        gen = self._gen

        def step(e):
            if gen == self._gen:
                fn(e)

        def done():
            if gen == self._gen and on_done is not None:
                on_done()

        animate(self, dur, step, easing=easing, on_done=done)

    def _tween_color(self, target, dur):
        if not self._manage_color:
            return
        start = self._cur_color
        self._cur_color = target
        # 色值变化用 ease_in_out（缓入缓出），过渡更自然、无突兀跳变
        self._anim(dur, lambda e: safe_configure(
            self._btn, fg_color=lerp_color(start, target, e)),
            easing=ease_in_out)

    def _place_btn(self, ry, scale=1.0):
        self._btn.place(relx=0.5, rely=ry, anchor="center",
                        relwidth=scale, relheight=scale)

    def _scale_shadow(self, s):
        self._shadow.place(relx=0.5, rely=0.5 + (SHADOW_OFFSET / self._bh) * 0.4 * s,
                           anchor="center", relwidth=s, relheight=s)

    def _ensure_shadow(self):
        if self._shadow_img is None:
            pil = make_shadow_image(self._bw, self._bh, radius=BTN_RADIUS,
                                    blur=SHADOW_BLUR, alpha=SHADOW_ALPHA,
                                    offset=SHADOW_OFFSET)
            self._shadow_img = ctk.CTkImage(pil, pil, (pil.width, pil.height))

    @property
    def _lift(self):
        return LIFT_PX / self._bh

    def _on_enter(self, _e):
        self._ensure_shadow()
        self._shadow.tkraise()
        self._btn.tkraise()
        safe_configure(self._shadow, image=self._shadow_img)
        self._tween_color(self._hover, DUR_HOVER)
        self._anim(DUR_HOVER, lambda e: self._place_btn(0.5 - self._lift * e))
        self._anim(DUR_HOVER, lambda e: self._scale_shadow(1.0 + 0.14 * e))

    def _on_leave(self, _e):
        self._tween_color(self._base, DUR_HOVER)
        self._anim(DUR_HOVER, lambda e: self._place_btn(0.5 - self._lift * (1 - e)))
        self._anim(DUR_HOVER, lambda e: self._scale_shadow(1.14 - 0.14 * e),
                   on_done=lambda: safe_configure(self._shadow, image=None))

    def _on_press(self, _e):
        self._tween_color(self._press, DUR_PRESS)
        self._anim(DUR_PRESS, lambda e: self._place_btn(0.5 - self._lift * (1 - 0.3 * e)))
        self._anim(DUR_PRESS, lambda e: self._scale_shadow(1.14 - 0.14 * 0.3 * e))

    def _on_release(self, _e):
        self._tween_color(self._hover, DUR_HOVER)
        self._anim(DUR_HOVER, lambda e: self._place_btn(0.5 - self._lift * e))
        self._anim(DUR_HOVER, lambda e: self._scale_shadow(1.0 + 0.14 * e))

    def _on_focus_in(self, _e):
        # 聚焦：按钮亮起圆角描边（无障碍可见焦点）
        safe_configure(self._btn, border_color="#0a6cf0", border_width=2)

    def _on_focus_out(self, _e):
        safe_configure(self._btn, border_width=0)

    def configure(self, **kw):
        if "state" in kw:
            safe_configure(self._btn, state=kw.pop("state"))
        if "text" in kw:
            safe_configure(self._btn, text=kw.pop("text"))
        return super().configure(**kw)


# ---------------- Windows 风格窗口控件 ----------------
class WindowsCaptionButton(ctk.CTkButton):
    """Windows 11 风格标题栏控件（最小化 / 最大化 / 关闭）。

    透明底、中性字形；悬停浅灰背景（关闭为红），按下更深；点击即生效，
    hover 以短补间过渡贴合原生手感。
    """

    def __init__(self, master, glyph: str, cmd, kind: str = "normal",
                 width: int = 46, height: int = 46, **kw):
        super().__init__(
            master, text=glyph, width=width, height=height, corner_radius=0,
            fg_color="#eef0f4", hover_color="#eef0f4",
            text_color="#1d1d1f", font=("Segoe UI Symbol", 15),
            command=cmd,
        )
        self._gen = 0
        self._kind = kind
        self._cur_fg = "#eef0f4"
        self._cur_txt = "#1d1d1f"
        if kind == "close":
            self._hover_fg, self._hover_txt = "#d83a2c", "#ffffff"
            self._press_fg, self._press_txt = "#b32a1e", "#ffffff"
        else:
            self._hover_fg, self._hover_txt = "#e3e3e8", "#1d1d1f"
            self._press_fg, self._press_txt = "#d6d6dc", "#1d1d1f"

        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._down)
        self.bind("<ButtonRelease-1>", self._up)

    def _tween(self, fg, txt, dur):
        self._gen += 1
        gen = self._gen
        start_fg, start_txt = self._cur_fg, self._cur_txt
        self._cur_fg, self._cur_txt = fg, txt

        def step(e):
            if gen != self._gen:
                return
            safe_configure(self, fg_color=lerp_color(start_fg, fg, e),
                           text_color=lerp_color(start_txt, txt, e))

        animate(self, dur, step, easing=ease_in_out)

    def _enter(self, _e):
        self._tween(self._hover_fg, self._hover_txt, DUR_HOVER)

    def _leave(self, _e):
        self._tween("#eef0f4", "#1d1d1f", DUR_HOVER)

    def _down(self, _e):
        self._tween(self._press_fg, self._press_txt, DUR_PRESS)

    def _up(self, _e):
        self._tween(self._hover_fg, self._hover_txt, DUR_HOVER)
