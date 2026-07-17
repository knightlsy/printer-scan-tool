"""冻结环境 fitz 渲染专项验证。

单独 onefile 打包后运行：确认 PyInstaller 把 pymupdf 原生 DLL
(mupdfcpp64.dll / _mupdf.pyd / _extra.pyd) 正确带进包，
且能在冻结 onefile 模式下 import fitz + 渲染 PDF 首页。
成功打印 FROZEN_FITZ_OK，失败打印 FROZEN_FITZ_FAIL + traceback。
"""
import sys
import traceback
from PIL import Image
import fitz


def main():
    try:
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((40, 100), "HELLO PDF")
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        print("FROZEN_FITZ_OK size=%s mode=%s" % (img.size, img.mode))
    except Exception:
        traceback.print_exc()
        print("FROZEN_FITZ_FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
