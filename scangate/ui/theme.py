"""统一设计令牌（Apple Design Language · 精致版）。

集中管理配色、字号、间距、圆角、阴影与动效时长，确保所有面板 / 顶栏 /
弹窗 / 遮罩 / 按钮风格一致。

设计语言：柔和中性色调 + 大圆角（卡片 22 / 按钮 16）+ 毛玻璃（半透明渐变磨砂
表面）+ 8px 基准间距 + 充足留白 + 流畅过渡（200–300ms）。

字体使用 tuple 字体（定义时不依赖 Tk 根窗口），避免「过早创建字体」错误。
"""

import customtkinter as ctk

# ---------------- 配色（统一冷蓝灰 · 高对比 · Apple 风） ----------------
# 全站统一于同一冷色相（蓝灰），杜绝「纯白面板 / 暖灰按钮」与冷灰背景的割裂。
# 根背景：冷蓝灰多段渐变（顶部冷白光源 → 底部略深冷灰）
BG_TOP  = "#fbfcfe"   # 顶部（冷白，光源处）
BG_MID  = "#eef1f7"   # 中部
BG_BOT  = "#e3e8f1"   # 底部（略深冷灰）

# 毛玻璃表面：冷白微透（与背景同色系，避免刺眼纯白割裂）+ 冷灰描边
GLASS_TINT   = "#f6f8fc"   # 磨砂填充色调（冷白，贴合背景色相）
GLASS_ALPHA  = 0.74        # 表面不透明度（越低越透、毛玻璃感越强）
GLASS_ALT    = "#eef1f8"   # 输入框 / 列表背景（冷中性）
GLASS_BORDER = "#c3c9d8"   # 玻璃描边（冷灰，与背景同色相）
GLASS_HI     = "#ffffff"   # 顶部高光线
GLASS        = "#f6f8fc"   # 兼容旧调用（冷白，用于弹窗兜底）
ERROR        = "#ff3b30"   # 错误（等同危险红，兼容旧调用）

# 主色：Apple 系统蓝（冷调，与整体一致）
ACCENT       = "#0a6cf0"   # 主蓝
ACCENT_HI    = "#2f83f5"   # hover（更亮）
ACCENT_PRESS = "#0858c7"   # 按下（更深）
ACCENT_SOFT  = "#e6f0fd"   # 主色浅底（透明 hover / 链接，冷调）
# 危险红（Apple 红，语义色保持暖以作区分）
DANGER       = "#ff3b30"
DANGER_HI    = "#ff453a"
DANGER_PRESS = "#e0352b"
# 次按钮灰（冷蓝灰，与背景 / 面板同色系，色调融合而非割裂）
GRAY_BTN     = "#e6e9f2"
GRAY_BTN_HI  = "#dfe3ee"
GRAY_BTN_PRESS = "#d4d9e6"

# 文字：Apple 近黑 + 冷调次级（满足 WCAG AA 对比度）
TEXT         = "#1d1d1f"   # 主文字（白底对比 ≈ 16:1）
TEXT_DIM     = "#51545e"   # 次级（冷灰，白底对比 ≈ 7:1，过 AA）
TEXT_FAINT   = "#6b6f7a"   # 弱化（冷灰，白底对比 ≈ 4.6:1，过 AA 普通文本）

# 状态色（Apple 语义色）
SUCCESS      = "#1f9d4d"   # 绿（加深以满足白底对比）
WARNING      = "#c77700"   # 橙（加深以满足白底对比）
INDIGO       = "#5e5ce6"   # 公司外链接强调（靛蓝）
INDIGO_HI    = "#6f6df0"

# ---------------- 圆角 / 描边 ----------------
RADIUS      = 22      # 卡片 / 面板大圆角
BTN_RADIUS  = 16      # 按钮大圆角（满足 16px 以上）
BORDER_W    = 1.5     # 统一描边宽度

# ---------------- 间距系统（8px 基准网格） ----------------
SP = {
    "xs": 4,    # 极紧
    "sm": 8,    # 紧
    "md": 16,   # 标准
    "lg": 24,   # 宽松
    "xl": 32,   # 区间
    "xxl": 40,  # 大区
}

# ---------------- 动效（毫秒，建议 200–300） ----------------
DUR_HOVER  = 220      # 悬停过渡
DUR_PRESS  = 140      # 按下过渡
DUR_FOCUS  = 200      # 聚焦过渡
LIFT_PX    = 2        # 悬停抬升像素
PRESS_SCALE = 0.97    # 按下微缩比例

# ---------------- 阴影（柔和、分层） ----------------
SHADOW_BLUR   = 26     # 模糊半径
SHADOW_ALPHA  = 0.18   # 不透明度
SHADOW_OFFSET = 10     # 垂直偏移

# ---------------- 字体（SF Pro → Segoe → 雅黑 回退栈） ----------------
# Windows 无 SF Pro，Segoe UI 是最接近的系统等价字体；
# 中文回退到「Microsoft YaHei UI」（雅黑），保证中文不会缺字。
_LATIN = "Segoe UI"            # 拉丁文（标题、版本号等）
_CJK   = "Microsoft YaHei UI"  # 中文（正文 / 区块标题）
_MONO  = "Consolas"            # 等宽（仅拉丁）

FONT = {
    "display": (_LATIN, 26, "bold"),   # 大标题（关于页）
    "title":   (_LATIN, 20, "bold"),   # 窗口 / 区块大标题
    "section": (_CJK, 15, "bold"),     # 区块标题
    "body":    (_CJK, 14),             # 正文
    "small":   (_CJK, 12),             # 辅助
    "caption": (_CJK, 11),             # 极弱说明
    "mono":    (_MONO, 13),            # 等宽
    "mono_sm": (_MONO, 12),            # 等宽小
}

# ---------------- 控件工厂 ----------------
def button(master, text: str = "", command=None, kind: str = "primary", **kw):
    """统一按钮入口（兼容旧调用），内部用 AppleButton 实现。"""
    from scangate.ui.fx import AppleButton
    return AppleButton(master, text=text, command=command, kind=kind, **kw)


def link_button(master, text: str = "", command=None, **kw):
    """文字链接样式（透明底、系统蓝、悬停浅蓝）。"""
    opts = dict(
        fg_color="transparent",
        hover_color=ACCENT_SOFT,
        text_color=ACCENT,
        font=FONT["body"],
        height=32,
        corner_radius=BTN_RADIUS,
    )
    opts.update(kw)
    return ctk.CTkButton(master, text=text, command=command, **opts)
