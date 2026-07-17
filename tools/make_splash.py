"""用 Pillow 渲染「液态玻璃」质感的启动图与设计稿（canvas-design 技能产出）。

- assets/splash.png：程序启动闪屏（PyInstaller --splash 使用，自带背景，非透明）
- design/liquid_glass_concept.png：设计参考稿（概念海报），作为视觉交付物

仅依赖 Pillow，纯静态绘制，无持续动画。
"""

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASSETS = os.path.join(_ROOT, "assets")
_DESIGN = os.path.join(_ROOT, "design")
os.makedirs(_ASSETS, exist_ok=True)
os.makedirs(_DESIGN, exist_ok=True)

LATIN = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segui.ttf"]
CJK = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"]


def _font(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _vgradient(w, h, top, bot):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        row = (r, g, b)
        for x in range(w):
            px[x, y] = row
    return img


def _rounded_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return m


def _blob_layer(w, h, blobs):
    """在透明层上画若干低透明度椭圆并高斯模糊，形成柔光色块。"""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for (cx, cy, rad, color, alpha) in blobs:
        step = max(3, rad // 14)
        for i in range(0, rad, step):
            a = int(alpha * (1 - i / rad))
            d.ellipse([cx - rad + i, cy - rad + i, cx + rad - i, cy + rad - i],
                      fill=(color[0], color[1], color[2], max(0, a)))
    return layer.filter(ImageFilter.GaussianBlur(70))


def _glass_card(base, x, y, w, h, r, fill=(255, 255, 255, 200), border=(210, 218, 227, 255)):
    """在 base 上贴一块磨砂玻璃卡片：半透白填充 + 顶部高光 + 浅灰描边。"""
    card = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, fill=fill)
    # 顶部高光
    d.line([x + r, y + 1, x + w - r, y + 1], fill=(255, 255, 255, 235), width=2)
    # 描边
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, outline=border, width=2)
    mask = _rounded_mask(w, h, r)
    region = Image.new("RGBA", base.size, (0, 0, 0, 0))
    region.paste(card.crop([x, y, x + w, y + h]), (x, y), mask)
    return Image.alpha_composite(base, region)


def render_splash(path, w=640, h=380):
    img = _vgradient(w, h, (236, 240, 247), (223, 230, 242))
    blobs = [
        (int(w * 0.28), int(h * 0.34), int(h * 0.62), (10, 132, 255), 70),
        (int(w * 0.78), int(h * 0.70), int(h * 0.55), (94, 92, 230), 55),
    ]
    img = Image.alpha_composite(img.convert("RGBA"), _blob_layer(w, h, blobs))

    cw, ch, cx0, cy0 = 380, 184, (w - 380) // 2, (h - 184) // 2
    img = _glass_card(img, cx0, cy0, cw, ch, 28).convert("RGB")

    d = ImageDraw.Draw(img)
    # 标题
    tfont = _font(LATIN, 46)
    title = "SCAN.GATE"
    tw = d.textlength(title, font=tfont)
    d.text((cx0 + (cw - tw) / 2, cy0 + 46), title, font=tfont, fill=(29, 29, 31))
    # 副标题（中文需 CJK 字体）
    cfont = _font(CJK, 17)
    sub = "打印机扫描共享工具"
    sw = d.textlength(sub, font=cfont)
    d.text((cx0 + (cw - sw) / 2, cy0 + 104), sub, font=cfont, fill=(110, 110, 115))
    # 细进度条图形
    bw, bh = 220, 6
    bx, by = cx0 + (cw - bw) / 2, cy0 + ch - 40
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3, fill=(226, 231, 240))
    d.rounded_rectangle([bx, by, bx + bw * 0.62, by + bh], radius=3, fill=(10, 132, 255))
    img.save(path)
    return path


def render_concept(path, w=960, h=600):
    img = _vgradient(w, h, (238, 242, 248), (220, 228, 240))
    blobs = [
        (int(w * 0.22), int(h * 0.30), int(h * 0.50), (10, 132, 255), 80),
        (int(w * 0.80), int(h * 0.72), int(h * 0.46), (94, 92, 230), 60),
        (int(w * 0.62), int(h * 0.20), int(h * 0.34), (52, 199, 89), 40),
    ]
    img = Image.alpha_composite(img.convert("RGBA"), _blob_layer(w, h, blobs))

    # 三块玻璃卡片（模拟三栏布局）
    cards = [
        (60, 90, 250, 420, "连接", (255, 255, 255, 205)),
        (330, 90, 320, 420, "文件", (255, 255, 255, 200)),
        (670, 90, 230, 420, "预览", (255, 255, 255, 195)),
    ]
    for (x, y, cw, chh, _t, fill) in cards:
        img = _glass_card(img, x, y, cw, chh, 30, fill=fill)

    d = ImageDraw.Draw(img)
    # 标题
    tfont = _font(LATIN, 40)
    title = "LIQUID GLASS"
    tw = d.textlength(title, font=tfont)
    d.text(((w - tw) / 2, 36), title, font=tfont, fill=(29, 29, 31))
    cfont = _font(CJK, 16)
    sub = "SCAN.GATE · 液态苹果风设计语言"
    sw = d.textlength(sub, font=cfont)
    d.text(((w - sw) / 2, 86), sub, font=cfont, fill=(110, 110, 115))

    # 卡片内极简标签
    lfont = _font(LATIN, 15)
    for (x, y, cw, chh, t, _f) in cards:
        d.text((x + 22, y + 22), t.upper(), font=lfont, fill=(10, 132, 255))
        # 几条占位条目（浅灰圆角条）
        yy = y + 70
        for i in range(4):
            d.rounded_rectangle([x + 22, yy, x + cw - 22, yy + 26], radius=8,
                                fill=(233, 237, 243))
            yy += 40

    # 细微参考标记
    mfont = _font(LATIN, 11)
    d.text((w - 150, h - 30), "fig.01 — frosted surface", font=mfont, fill=(142, 142, 147))
    d.text((30, h - 30), "Liquid Glass / v3", font=mfont, fill=(142, 142, 147))
    img.save(path)
    return path


if __name__ == "__main__":
    p1 = render_splash(os.path.join(_ASSETS, "splash.png"))
    p2 = render_concept(os.path.join(_DESIGN, "liquid_glass_concept.png"))
    print("splash ->", p1)
    print("concept ->", p2)
