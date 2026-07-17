"""预览生成服务（后台执行）。

- 图片：用 Pillow 打开并缩放到适合预览的尺寸（单页，无翻页）。
- PDF：惰性导入 fitz (PyMuPDF) 渲染指定页；若未安装则抛 ModuleNotFoundError，
  由 UI 层降级提示。
统一签名 (progress, cancel, path, page=0)。

返回值（dict）：
    {
        "image": PIL.Image | None,  # 渲染结果，失败/不支持时为 None
        "page":  int,               # 实际渲染的页码（已夹紧到合法区间，0 基）
        "total": int,               # 文档总页数（图片恒为 1，空 PDF 为 0）
        "pdf":   bool,              # 是否为多页 PDF（决定是否显示翻页控件）
    }
"""

import os
from typing import Callable

from PIL import Image

MAX_SIZE = (560, 720)

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp")


def make_preview(progress: Callable, cancel, path: str, page: int = 0, max_size=MAX_SIZE):
    ext = os.path.splitext(path)[1].lower()
    progress(20, "生成预览…")
    if cancel.is_cancelled():
        raise InterruptedError()

    if ext in IMAGE_EXTS:
        img = Image.open(path)
        if img.mode in ("RGBA", "P", "CMYK"):
            img = img.convert("RGB")
        img.thumbnail(max_size)
        progress(100, "完成")
        return {"image": img, "page": 0, "total": 1, "pdf": False}

    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ModuleNotFoundError(
                "PDF 预览需要 PyMuPDF（fitz）。当前未安装，请在命令行执行 "
                "`pip install pymupdf` 后重试，或直接用外部阅读器打开该文件。"
            )
        doc = fitz.open(path)
        try:
            total = doc.page_count
            if total == 0:
                progress(100, "完成")
                return {"image": None, "page": 0, "total": 0, "pdf": True}
            page = max(0, min(int(page), total - 1))
            pg = doc.load_page(page)
            pix = pg.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.thumbnail(max_size)
        finally:
            doc.close()
        progress(100, "完成")
        return {"image": img, "page": page, "total": total, "pdf": True}

    raise ValueError(f"暂不支持预览该文件类型: {ext}")
