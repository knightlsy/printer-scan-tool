"""Web 混合版程序入口（pywebview + HTML/CSS 前端）。

- 先检查单实例（Windows 命名互斥体），重复启动直接提示并退出
- 启动 pywebview 窗口（HTML/CSS 真·毛玻璃前端 + Python 后端）
- 通过 sys.path 注入项目根，保证 import scangate 在源码 / 打包两种形态下都可用
"""

import os
import sys

# 将项目根目录（scangate 的父目录）加入 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scangate.core.singleton import is_already_running, show_already_running
from scangate.web.app import run
from scangate.installer import maybe_install_and_relaunch


def main():
    if is_already_running():
        show_already_running()
        return
    # 首次运行（来自便携/解压目录）自动安装到本机并重启，保证只跑「已安装」副本
    if maybe_install_and_relaunch():
        return
    run()


if __name__ == "__main__":
    main()
