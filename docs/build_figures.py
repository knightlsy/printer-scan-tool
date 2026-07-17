# -*- coding: utf-8 -*-
"""Generate schematic SVG figures for the SCAN.GATE user guide.
These are style-consistent mockups (Liquid Glass), clearly labeled as
schematic, standing in for real screenshots the user will capture on their PC.
"""
import os

OUT = r"C:\Users\EDY\WorkBuddy\2026-07-07-10-57-44\printer-scan-tool\docs\images"
os.makedirs(OUT, exist_ok=True)

ACCENT = "#2f6bff"; ACCENT2 = "#5689ff"; INK = "#1f2d4d"; SUB = "#5a6a88"
DANGER = "#ff4d4f"; GREEN = "#1fa463"

DEFS = '''<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#eef2f9"/><stop offset="1" stop-color="#d8e2f2"/>
  </linearGradient>
  <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#5689ff"/><stop offset="1" stop-color="#2f6bff"/>
  </linearGradient>
  <filter id="glass" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="6" result="b"/>
    <feComponentTransfer><feFuncA type="linear" slope="0.55"/></feComponentTransfer>
  </filter>
  <radialGradient id="blobA" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#9fc0ff" stop-opacity="0.7"/><stop offset="1" stop-color="#9fc0ff" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="blobB" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#c7b8ff" stop-opacity="0.6"/><stop offset="1" stop-color="#c7b8ff" stop-opacity="0"/>
  </radialGradient>
</defs>'''

FONT = "font-family=\"'Segoe UI','Microsoft YaHei',sans-serif\""


def highlight(x, y, w, h, label, anchor="left"):
    """Dashed accent rectangle + label pointing at the region."""
    lx = x + 8 if anchor == "left" else x + w - 8
    ta = "start" if anchor == "left" else "end"
    return f'''<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{ACCENT}" stroke-width="2.5" stroke-dasharray="7 5"/>
  <rect x="{lx-4 if anchor=='left' else lx- (len(label)*13)-12}" y="{y-26}" width="{len(label)*13+18}" height="20" rx="6" fill="{ACCENT}"/>
  <text x="{lx+3 if anchor=='left' else lx-3}" y="{y-12}" font-size="12" fill="#fff" text-anchor="{ta}">{label}</text>'''


def window_base(connected=True, preview_doc=False, corner_cursor=None, highlights=None):
    status_text = "已连接" if connected else "未连接"
    status_color = GREEN if connected else DANGER
    banner_text = "已连接" if connected else "就绪"
    banner_color = "#42634f" if connected else "#7a89a8"
    hl = ""
    if highlights:
        hl = "".join(highlights)

    preview_inner = ""
    if preview_doc:
        preview_inner = '''
    <rect x="686" y="150" width="232" height="300" rx="10" fill="#ffffff" fill-opacity="0.95"/>
    <rect x="700" y="166" width="204" height="14" rx="3" fill="#cdd8ee"/>
    <rect x="700" y="188" width="180" height="10" rx="3" fill="#dde6f5"/>
    <rect x="700" y="206" width="200" height="10" rx="3" fill="#dde6f5"/>
    <rect x="700" y="224" width="150" height="10" rx="3" fill="#dde6f5"/>
    <rect x="700" y="250" width="204" height="120" rx="6" fill="#eef2fb"/>
    <rect x="700" y="380" width="120" height="10" rx="3" fill="#dde6f5"/>
    <rect x="700" y="398" width="170" height="10" rx="3" fill="#dde6f5"/>
    <rect x="760" y="430" width="112" height="28" rx="14" fill="#eef2fb"/>
    <text x="802" y="449" font-size="12" fill="#5a6a88" text-anchor="middle">‹ 上一页 / 下一页 ›</text>'''
    else:
        preview_inner = '''
    <rect x="686" y="200" width="232" height="300" rx="10" fill="#ffffff" fill-opacity="0.45"/>
    <text x="802" y="356" font-size="12" fill="#9aa7c0" text-anchor="middle">暂无预览</text>'''

    cursor = ""
    if corner_cursor:
        # draw a diagonal resize arrow cursor near bottom-right corner
        cx, cy = 930, 568
        cursor = f'''
    <g transform="translate({cx},{cy})">
      <path d="M0,0 L0,16 M0,0 L16,0 M0,0 L-5,5 M0,0 L5,-5" stroke="#1f2d4d" stroke-width="2" fill="none"/>
      <circle cx="0" cy="0" r="2.5" fill="#1f2d4d"/>
      <text x="22" y="-6" font-size="11" fill="#1f2d4d">拖拽缩放</text>
    </g>'''

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 600" {FONT}>
  {DEFS}
  <rect width="960" height="600" fill="url(#bg)"/>
  <circle cx="180" cy="120" r="220" fill="url(#blobA)"/>
  <circle cx="820" cy="500" r="240" fill="url(#blobB)"/>
  <rect x="0" y="0" width="960" height="50" fill="#ffffff" fill-opacity="0.55" filter="url(#glass)"/>
  <circle cx="28" cy="25" r="7" fill="url(#accent)"/>
  <circle cx="28" cy="25" r="12" fill="#5689ff" fill-opacity="0.25"/>
  <text x="44" y="30" font-size="16" font-weight="700" fill="{INK}">SCAN.GATE</text>
  <text x="138" y="30" font-size="12" fill="{SUB}">v4.0.0</text>
  <rect x="360" y="14" width="84" height="22" rx="11" fill="{status_color}" fill-opacity="0.12"/>
  <circle cx="376" cy="25" r="4" fill="{status_color}"/>
  <text x="388" y="29" font-size="11" fill="{status_color}">{status_text}</text>
  <rect x="852" y="16" width="22" height="18" rx="4" fill="#ffffff" fill-opacity="0.7"/>
  <rect x="878" y="16" width="22" height="18" rx="4" fill="#ffffff" fill-opacity="0.7"/>
  <rect x="904" y="16" width="22" height="18" rx="4" fill="#ff6b6b" fill-opacity="0.85"/>
  <rect x="320" y="62" width="80" height="22" rx="11" fill="#ffffff" fill-opacity="0.6"/>
  <circle cx="334" cy="73" r="4" fill="{GREEN if connected else '#9aa7c0'}"/>
  <text x="344" y="77" font-size="11" fill="{banner_color}">{banner_text}</text>
  <rect x="24" y="96" width="270" height="480" rx="14" fill="#ffffff" fill-opacity="0.6" filter="url(#glass)"/>
  <text x="42" y="124" font-size="14" font-weight="700" fill="{INK}">连接设置</text>
  <rect x="240" y="110" width="42" height="22" rx="6" fill="#ffffff" fill-opacity="0.8"/>
  <text x="252" y="125" font-size="11" fill="#3a4a6a">管理</text>
  <text x="42" y="158" font-size="11" fill="{SUB}">服务器地址</text>
  <rect x="42" y="164" width="234" height="26" rx="6" fill="#ffffff" fill-opacity="0.9"/>
  <text x="50" y="181" font-size="12" fill="#2a3a58">192.168.4.82</text>
  <text x="42" y="208" font-size="11" fill="{SUB}">共享名</text>
  <rect x="42" y="214" width="234" height="26" rx="6" fill="#ffffff" fill-opacity="0.9"/>
  <text x="50" y="231" font-size="12" fill="#2a3a58">share</text>
  <text x="42" y="258" font-size="11" fill="{SUB}">子目录</text>
  <rect x="42" y="264" width="234" height="26" rx="6" fill="#ffffff" fill-opacity="0.9"/>
  <text x="50" y="281" font-size="12" fill="#2a3a58">PDF</text>
  <text x="42" y="308" font-size="11" fill="{SUB}">用户名</text>
  <rect x="42" y="314" width="234" height="26" rx="6" fill="#ffffff" fill-opacity="0.9"/>
  <text x="50" y="331" font-size="12" fill="#2a3a58">share</text>
  <text x="42" y="358" font-size="11" fill="{SUB}">密码</text>
  <rect x="42" y="364" width="234" height="26" rx="6" fill="#ffffff" fill-opacity="0.9"/>
  <text x="50" y="381" font-size="12" fill="#2a3a58">••••••</text>
  <rect x="42" y="408" width="234" height="34" rx="8" fill="url(#accent)"/>
  <text x="138" y="430" font-size="13" font-weight="700" fill="#fff" text-anchor="middle">连接共享</text>
  <rect x="42" y="450" width="234" height="32" rx="8" fill="#e9eef8"/>
  <text x="138" y="471" font-size="13" fill="#3a4a6a" text-anchor="middle">断开连接</text>
  <rect x="42" y="490" width="234" height="30" rx="8" fill="#ffffff" fill-opacity="0.7"/>
  <text x="138" y="510" font-size="12" fill="{SUB}" text-anchor="middle">关于程序</text>
  <rect x="312" y="96" width="340" height="480" rx="14" fill="#ffffff" fill-opacity="0.6" filter="url(#glass)"/>
  <text x="330" y="124" font-size="14" font-weight="700" fill="{INK}">文件列表</text>
  <rect x="330" y="140" width="50" height="26" rx="6" fill="url(#accent)"/>
  <text x="355" y="157" font-size="11" fill="#fff" text-anchor="middle">刷新</text>
  <rect x="386" y="140" width="50" height="26" rx="6" fill="url(#accent)"/>
  <text x="411" y="157" font-size="11" fill="#fff" text-anchor="middle">上传</text>
  <rect x="442" y="140" width="50" height="26" rx="6" fill="url(#accent)"/>
  <text x="467" y="157" font-size="11" fill="#fff" text-anchor="middle">下载</text>
  <rect x="498" y="140" width="50" height="26" rx="6" fill="#ff6b6b" fill-opacity="0.85"/>
  <text x="523" y="157" font-size="11" fill="#fff" text-anchor="middle">删除</text>
  <text x="330" y="190" font-size="11" fill="{SUB}">名称</text>
  <text x="560" y="190" font-size="11" fill="{SUB}" text-anchor="middle">大小</text>
  <text x="630" y="190" font-size="11" fill="{SUB}" text-anchor="end">修改时间</text>
  <rect x="330" y="200" width="304" height="30" rx="6" fill="#2f6bff" fill-opacity="0.10"/>
  <text x="336" y="220" font-size="12" fill="#2a3a58">扫描件_20260709_001.pdf</text>
  <text x="560" y="220" font-size="12" fill="{SUB}" text-anchor="middle">1.2 MB</text>
  <text x="630" y="220" font-size="11" fill="{SUB}" text-anchor="end">07-09 10:30</text>
  <rect x="330" y="234" width="304" height="30" rx="6" fill="#ffffff" fill-opacity="0.5"/>
  <text x="336" y="254" font-size="12" fill="#2a3a58">月度报表_Q2.pdf</text>
  <text x="560" y="254" font-size="12" fill="{SUB}" text-anchor="middle">3.8 MB</text>
  <text x="630" y="254" font-size="11" fill="{SUB}" text-anchor="end">07-08 16:12</text>
  <rect x="330" y="268" width="304" height="30" rx="6" fill="#ffffff" fill-opacity="0.5"/>
  <text x="336" y="288" font-size="12" fill="#2a3a58">合同扫描件.pdf</text>
  <text x="560" y="288" font-size="12" fill="{SUB}" text-anchor="middle">820 KB</text>
  <text x="630" y="288" font-size="11" fill="{SUB}" text-anchor="end">07-07 09:45</text>
  <rect x="668" y="96" width="268" height="480" rx="14" fill="#ffffff" fill-opacity="0.6" filter="url(#glass)"/>
  <text x="686" y="124" font-size="14" font-weight="700" fill="{INK}">预览</text>
  {preview_inner}
  {cursor}
  {hl}
</svg>'''


def modal(title, body_lines, buttons, w=560, h=360, x=200, y=130):
    """App-style custom modal (white glass card on dim backdrop)."""
    btns = ""
    bw = 110
    total = len(buttons) * bw + (len(buttons) - 1) * 14
    start_x = x + w - total - 24
    for i, (label, primary) in enumerate(buttons):
        bx = start_x + i * (bw + 14)
        by = y + h - 56
        fill = "url(#accent)" if primary else "#e9eef8"
        tc = "#fff" if primary else "#3a4a6a"
        btns += f'<rect x="{bx}" y="{by}" width="{bw}" height="32" rx="8" fill="{fill}"/>' \
                f'<text x="{bx+bw//2}" y="{by+21}" font-size="13" fill="{tc}" text-anchor="middle">{label}</text>'
    body = ""
    for i, ln in enumerate(body_lines):
        body += f'<text x="{x+24}" y="{y+96+i*26}" font-size="13" fill="{SUB}">{ln}</text>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 600" {FONT}>
  {DEFS}
  <rect width="960" height="600" fill="url(#bg)"/>
  <rect width="960" height="600" fill="#000" fill-opacity="0.18"/>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#ffffff" fill-opacity="0.95" filter="url(#glass)"/>
  <text x="{x+24}" y="{y+38}" font-size="16" font-weight="700" fill="{INK}">{title}</text>
  <text x="{x+w-24}" y="{y+38}" font-size="20" fill="#9aa7c0" text-anchor="middle">×</text>
  {body}
  {btns}
</svg>'''


def win_dialog(title, body, buttons, w=560, h=400, x=200, y=110):
    """Native Windows-style file dialog mockup (blue title bar)."""
    btns = ""
    bw = 92
    total = len(buttons) * bw + (len(buttons) - 1) * 12
    start_x = x + w - total - 20
    for i, (label, primary) in enumerate(buttons):
        bx = start_x + i * (bw + 12)
        by = y + h - 46
        fill = "url(#accent)" if primary else "#e9eef8"
        tc = "#fff" if primary else "#3a4a6a"
        btns += f'<rect x="{bx}" y="{by}" width="{bw}" height="30" rx="4" fill="{fill}"/>' \
                f'<text x="{bx+bw//2}" y="{by+20}" font-size="12" fill="{tc}" text-anchor="middle">{label}</text>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 600" {FONT}>
  <rect width="960" height="600" fill="#dfe6f2"/>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#ffffff" stroke="#b9c4dc"/>
  <rect x="{x}" y="{y}" width="{w}" height="34" rx="8" fill="url(#accent)"/>
  <rect x="{x}" y="{y+18}" width="{w}" height="16" fill="url(#accent)"/>
  <text x="{x+14}" y="{y+22}" font-size="13" fill="#fff" font-weight="600">{title}</text>
  <text x="{x+w-14}" y="{y+22}" font-size="15" fill="#fff" text-anchor="middle">×</text>
  {body}
  {btns}
</svg>'''


# ---------- figure content ----------

# Step 1: connected window (green light + populated list)
fig1 = window_base(connected=True,
                   highlights=[highlight(354, 8, 96, 34, "① 指示灯变绿"),
                               highlight(310, 94, 344, 484, "② 文件列表出现")])

# Step 2: file list focus
fig2 = window_base(connected=True,
                   highlights=[highlight(310, 132, 344, 150, "文件列表：名称/大小/修改时间 三列")])

# Step 3: preview focus
fig3 = window_base(connected=True, preview_doc=True,
                   highlights=[highlight(666, 94, 272, 484, "右侧预览：文档图像 + 翻页控件")])

# Step 4: download Save-As dialog
body4 = '''
  <rect x="220" y="150" width="520" height="170" rx="4" fill="#f4f7fc" stroke="#cdd8ee"/>
  <text x="234" y="172" font-size="11" fill="#7a89a8">导航窗格</text>
  <rect x="234" y="184" width="150" height="14" rx="3" fill="#dde6f5"/>
  <rect x="234" y="204" width="120" height="14" rx="3" fill="#dde6f5"/>
  <rect x="234" y="224" width="140" height="14" rx="3" fill="#dde6f5"/>
  <text x="404" y="172" font-size="11" fill="#7a89a8">文件夹内容</text>
  <rect x="404" y="184" width="320" height="16" rx="3" fill="#ffffff" stroke="#cdd8ee"/>
  <rect x="404" y="208" width="320" height="14" rx="3" fill="#eef2fb"/>
  <rect x="404" y="228" width="290" height="14" rx="3" fill="#eef2fb"/>
  <text x="220" y="346" font-size="12" fill="#3a4a6a">文件名(N):</text>
  <rect x="300" y="334" width="380" height="26" rx="4" fill="#fff" stroke="#9fb3d8"/>
  <text x="308" y="352" font-size="12" fill="#2a3a58">扫描件_20260709_001.pdf</text>
  <text x="220" y="392" font-size="12" fill="#3a4a6a">保存类型(T):</text>
  <rect x="300" y="380" width="220" height="26" rx="4" fill="#fff" stroke="#9fb3d8"/>
  <text x="308" y="398" font-size="12" fill="#2a3a58">PDF 文件 (*.pdf)</text>'''
fig4 = win_dialog("另存为", body4, [("保存", True), ("取消", False)], w=560, h=440, x=200, y=90)

# Step 5: upload Open dialog (multi-select)
body5 = '''
  <rect x="220" y="150" width="520" height="180" rx="4" fill="#f4f7fc" stroke="#cdd8ee"/>
  <text x="234" y="172" font-size="11" fill="#7a89a8">文件夹内容（可多选）</text>
  <rect x="234" y="184" width="490" height="16" rx="3" fill="#ffffff" stroke="#cdd8ee"/>
  <rect x="248" y="184" width="14" height="14" rx="2" fill="#2f6bff"/>
  <text x="270" y="196" font-size="12" fill="#2a3a58">回执_已签字.pdf</text>
  <rect x="234" y="206" width="490" height="16" rx="3" fill="#eef2fb"/>
  <rect x="248" y="206" width="14" height="14" rx="2" fill="#2f6bff"/>
  <text x="270" y="218" font-size="12" fill="#2a3a58">报销单_07月.pdf</text>
  <rect x="234" y="228" width="490" height="16" rx="3" fill="#ffffff" stroke="#cdd8ee"/>
  <rect x="248" y="228" width="14" height="14" rx="2" fill="#fff" stroke="#9fb3d8"/>
  <text x="270" y="240" font-size="12" fill="#2a3a58">会议纪要.pdf</text>
  <rect x="234" y="250" width="490" height="16" rx="3" fill="#eef2fb"/>
  <rect x="248" y="250" width="14" height="14" rx="2" fill="#fff" stroke="#9fb3d8"/>
  <text x="270" y="262" font-size="12" fill="#2a3a58">合同附件.pdf</text>
  <text x="220" y="356" font-size="12" fill="#3a4a6a">文件名(N):</text>
  <rect x="300" y="344" width="380" height="26" rx="4" fill="#fff" stroke="#9fb3d8"/>
  <text x="308" y="362" font-size="12" fill="#2a3a58">回执_已签字.pdf; 报销单_07月.pdf</text>
  <text x="220" y="402" font-size="12" fill="#3a4a6a">文件类型(T):</text>
  <rect x="300" y="390" width="220" height="26" rx="4" fill="#fff" stroke="#9fb3d8"/>
  <text x="308" y="408" font-size="12" fill="#2a3a58">所有文件 (*.*)</text>'''
fig5 = win_dialog("打开", body5, [("打开", True), ("取消", False)], w=560, h=450, x=200, y=85)

# Step 6: delete confirm (custom app modal)
fig6 = modal("确认删除",
              ["确定要删除文件：",
               "「扫描件_20260709_001.pdf」吗？",
               "此操作不可恢复，且会写入溯源日志。"],
              [("确定", True), ("取消", False)], w=520, h=240, x=220, y=180)

# Step 8: resize cursor at corner
fig8 = window_base(connected=True, corner_cursor=True,
                   highlights=[highlight(902, 540, 56, 56, "右下角斜向缩放箭头", anchor="right")])

# Step 9a: about dialog
fig9a = modal("关于 SCAN.GATE",
              ["软件名称：SCAN.GATE 打印机扫描共享工具",
               "版本：v4.0.0",
               "作者：张三  （点击联系）",
               "版权：© 2026 内部工具 · 仅供公司使用"],
              [("关闭", False)], w=520, h=300, x=220, y=160)

# Step 9b: identity choice dialog
fig9b = modal("选择身份",
              ["请选择您的身份以联系作者："],
              [("公司内", True), ("公司外", False)], w=460, h=220, x=250, y=200)

figures = {
    "fg_step1.svg": fig1,
    "fg_step2.svg": fig2,
    "fg_step3.svg": fig3,
    "fg_step4.svg": fig4,
    "fg_step5.svg": fig5,
    "fg_step6.svg": fig6,
    "fg_step8.svg": fig8,
    "fg_step9a.svg": fig9a,
    "fg_step9b.svg": fig9b,
}

for name, svg in figures.items():
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", name, len(svg), "bytes")
print("DONE")
