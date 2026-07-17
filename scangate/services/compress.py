"""PDF 压缩服务（后台执行）。

- 用 PyMuPDF (fitz) 重写/重光栅化 PDF 以减小体积。
- 标准：垃圾回收 + deflate 压缩 + 清理冗余 + 压缩字体/图片数据流（画质无损）。
- 高压缩：把每页重新光栅化为约 150dpi 的图片嵌入新 PDF（对扫描件/图片型 PDF
  效果最好，体积更小；代价是文字不再可选、画质略降）。
- 惰性导入 fitz，避免影响程序启动速度。
- 统一签名 (src, dst, level, progress) → 返回 (原始字节数, 压缩后字节数)。
"""

import os
from typing import Callable, Tuple


def _human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.2f} MB"


def _rasterize_compress(doc, dst: str, dpi: float = 108, progress: Callable = None) -> None:
    """高压缩：逐页重光栅化为图片后重建 PDF（适合扫描件）。

    dpi 控制光栅化分辨率：越低体积越小、画质越糙。
    """
    import fitz
    new = fitz.open()
    total = doc.page_count
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    for i, page in enumerate(doc):
        if progress:
            progress(45 + int(45 * i / max(1, total)),
                     f"压缩第 {i + 1}/{total} 页…")
        pix = page.get_pixmap(matrix=mat)
        p = new.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, pixmap=pix)
    if progress:
        progress(95, "保存…")
    new.save(dst, garbage=4, deflate=True, clean=True, deflate_images=True)
    new.close()


def _rate_to_dpi(rate) -> float:
    """自定义压缩率(0-100) → 光栅化 DPI。

    100 = 最大压缩（低清，60dpi），0 = 最小压缩（高清，200dpi）。
    """
    try:
        rate = int(rate)
    except (TypeError, ValueError):
        rate = 70
    rate = max(0, min(100, rate))
    return 60 + (100 - rate) / 100.0 * 140


def compress(src: str, dst: str, level: str = "standard", rate: int = None,
            progress: Callable = None) -> Tuple[int, int]:
    """把 src 压缩后写入 dst，返回 (原始大小, 压缩后大小)。

    level:
      "standard" —— 清理冗余对象、压缩字体/图片数据流，画质无损。
      "high"     —— 重新光栅化每页（约 150dpi），体积更小（适合扫描件）。
      "custom"   —— 按 rate(0-100) 自定义光栅化分辨率。
    """
    if progress:
        progress(10, "打开 PDF…")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ModuleNotFoundError(
            "PDF 压缩需要 PyMuPDF（fitz）。请在命令行执行 "
            "`pip install pymupdf` 后重试。"
        )

    doc = fitz.open(src)
    try:
        if level == "high":
            _rasterize_compress(doc, dst, dpi=108, progress=progress)
            # 回退：光栅化后反而更大（文本型 PDF，光栅化无收益），改用无损压缩
            if progress:
                progress(92, "校验体积…")
            if os.path.getsize(dst) >= os.path.getsize(src):
                doc.save(
                    dst,
                    garbage=4, deflate=True, clean=True,
                    deflate_fonts=True, deflate_images=True,
                )
        elif level == "custom":
            dpi = _rate_to_dpi(rate)
            if progress:
                progress(30, f"按 {int(round(dpi))}dpi 压缩…")
            _rasterize_compress(doc, dst, dpi=dpi, progress=progress)
            # 自定义级别尊重用户选择：不做自动回退（如未变小会在状态栏提示）
        else:
            if progress:
                progress(45, "压缩中…")
            doc.save(
                dst,
                garbage=4,        # 最大垃圾回收
                deflate=True,     # 通用 deflate 压缩
                clean=True,        # 清理未使用对象/冗余
                deflate_fonts=True,
                deflate_images=True,
            )
    finally:
        doc.close()

    if progress:
        progress(100, "完成")
    return os.path.getsize(src), os.path.getsize(dst)


def human(n: int) -> str:
    return _human(n)
