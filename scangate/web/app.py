"""pywebview 启动引导。

- 解析 static 资源目录（开发态取源码目录；PyInstaller 单文件态取 sys._MEIPASS）。
- 用 file:// 加载 index.html（相对引用的 style.css / app.js 自动生效）。
- 创建无额外边框的窗口并挂上 Api 桥，最后启动事件循环。
"""

import os
import sys
import shutil

import webview

from scangate.web.api import Api
from scangate.config import APP_TITLE, VERSION, CONFIG_PATH


def _seed_default_config() -> None:
    """首次启动种子化：若本机尚无配置文件，则用内置默认配置初始化。

    这样在其他电脑上开箱即用（预置好服务器档），且绝不覆盖目标机已有配置。
    """
    if os.path.exists(CONFIG_PATH):
        return
    if getattr(sys, "_MEIPASS", None):
        src = os.path.join(sys._MEIPASS, "scangate", "web", "default_config.json")
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        src = os.path.join(here, "default_config.json")
    if not os.path.exists(src):
        return
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        shutil.copy(src, CONFIG_PATH)
    except Exception:
        pass


def _static_dir() -> str:
    """定位 static 目录：frozen 态在 sys._MEIPASS 下，开发态在源码目录。"""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "scangate", "web", "static")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "static")


def run() -> None:
    _seed_default_config()

    static_dir = _static_dir()
    index_path = os.path.join(static_dir, "index.html")
    url = "file:///" + os.path.abspath(index_path).replace("\\", "/")

    api = Api()
    webview.create_window(
        title=f"{APP_TITLE} v{VERSION}",
        url=url,
        js_api=api,
        width=1180,
        height=720,
        min_size=(760, 480),
        background_color="#e7edf6",
        # 无边框窗口：由前端自定义标题栏 + 拖拽区域接管。
        # easy_drag=False 关闭 pywebview 的「全局 mousedown 即拖拽」，
        # 仅保留基于 DRAG_REGION_SELECTOR(.pywebview-drag-region) 的「标题栏内才可拖拽」机制，
        # 从而内容区域不会被误拖。
        frameless=True,
        easy_drag=False,
    )
    # gui=None：Windows 上自动选用 Edge WebView2（需系统已带 WebView2 运行时）。
    webview.start(gui=None)
