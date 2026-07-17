"""从多尺寸 PNG 组装 SCAN.GATE 多分辨率 .ico 文件（含 256/48/32/16）。
同时输出关于对话框 logo（品牌光点）、favicon、单色版。
"""
import os
from pathlib import Path
from PIL import Image

DIR = Path(__file__).resolve().parent

# ── 1) 主图标 .ico（替换项目根目录 scan_gate_icon.ico）───────────────
ico_sizes = [256, 48, 32, 16]
imgs = []
for s in ico_sizes:
    p = DIR / f"icon_{s}.png"
    img = Image.open(p).convert("RGBA")
    # Windows ICO 要求尺寸精确匹配
    if img.size != (s, s):
        img = img.resize((s, s), Image.LANCZOS)
    imgs.append(img)

out_ico = DIR / "scan_gate_icon_v3.ico"
out_ico_root = DIR.parent.parent / "scan_gate_icon_v3.ico"  # 项目根目录

for fp in [out_ico, out_ico_root]:
    imgs[0].save(fp, format="ICO", append_images=imgs[1:], sizes=[(i.size[0], i.size[0]) for i in imgs])
    print(f"ICO → {fp} ({fp.stat().st_size:,} bytes)")

# ── 2) 关于对话框品牌 logo（仅光点 + 光晕，透明背景） ─────────────
logo_w, logo_h = 512, 512
from PIL import ImageDraw, ImageFilter
logo = Image.new("RGBA", (logo_w, logo_h), (0, 0, 0, 0))
draw = ImageDraw.Draw(logo)
cx, cy = logo_w // 2 - 10, logo_h // 2
orb_r, halo_r = 90, 150

# 光晕（accent-soft）
halo = Image.new("RGBA", (logo_w, logo_h), (0, 0, 0, 0))
hd = ImageDraw.Draw(halo)
hd.ellipse([cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r],
           fill=(47, 107, 255, 35))
halo = halo.filter(ImageFilter.GaussianBlur(30))

# 光点本体：渐变用径向模拟
orb_img = Image.new("RGBA", (orb_r * 3, orb_r * 3), (0, 0, 0, 0))
od = ImageDraw.Draw(orb_img)
ocx, ocy = orb_r * 1.5, orb_r * 1.5
for r in range(orb_r, 0, -1):
    t = r / orb_r
    if t < 0.5:
        # 核心→中间：#7ea7ff → #2f6bff
        c = tuple(int(a + (b - a) * (t * 2)) for a, b in zip((126, 167, 255), (47, 107, 255)))
    else:
        # 边缘：#2f6bff → #1f54e0
        c = tuple(int(a + (b - a) * ((t - 0.5) * 2)) for a, b in zip((47, 107, 255), (31, 84, 224)))
    od.ellipse([ocx - r, ocy - r, ocx + r, ocy + r], fill=c)

# 高光点
hl_r = int(orb_r * 0.18)
hl_off = int(orb_r * 0.25)
od.ellipse([ocx - hl_off - hl_r, ocy - hl_off - hl_r,
            ocx - hl_off + hl_r, ocy - hl_off + hl_r], fill=(255, 255, 255, 215))

# 裁切并合成
orb_crop = orb_img.crop((ocx - orb_r, ocy - orb_r, ocx + orb_r, ocy + orb_r))
logo.paste(halo, (cx - halo_r, cy - halo_r), halo)
logo.paste(orb_crop, (cx - orb_r, cy - orb_r), orb_crop)

logo_path = DIR / "scan_gate_logo.png"
logo_path_512 = DIR / "scan_gate_logo_512.png"
logo.save(logo_path, "PNG")
logo.save(logo_path_512, "PNG")
print(f"Logo → {logo_path}")

# ── 3) favicon（简化版：小瓷砖 + 简括号/束/点）────────────────────
fav_sizes = [64, 48, 32, 16]
fav_imgs = []
for s in fav_sizes:
    p = DIR / f"icon_{min(s, 32)}.png"  # 用小字形
    fav_imgs.append(Image.open(p).convert("RGBA").resize((s, s), Image.LANCZOS))
fav_path = DIR / "favicon.ico"
fav_imgs[0].save(fav_path, format="ICO",
                 append_images=fav_imgs[1:],
                 sizes=[(i.size[0], i.size[0]) for i in fav_imgs])
print(f"Favicon → {fav_path}")

# ── 4) 单色高对比度版（纯 accent 蓝，白色描边）────────────────────
mono_fp = DIR / "scan_gate_icon_mono.png"
mono_img = Image.open(DIR / "icon_256.png").convert("RGBA")
w, h = mono_img.size
pixels = mono_img.load()
threshold = 200
for y in range(h):
    for x in range(w):
        r, g, b, a = pixels[x, y]
        if a < 20:
            continue
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if b > r + 15 and b > g + 15:
            pixels[x, y] = (47, 107, 255, min(a + 40, 255))
        elif lum > threshold:
            pixels[x, y] = (255, 255, 255, a)
        else:
            pixels[x, y] = (47, 107, 255, int(a * 0.65))

mono_img.save(mono_fp, "PNG")
print(f"Mono  → {mono_fp}")

print("\nAll icon assets built.")
