"""程序入口。

- 先做单实例检查（互斥体），重复启动直接提示并退出
- 启动主窗口事件循环
- 通过 sys.path 注入项目根，保证 `import scangate` 在源码/打包两种形态下都可用
"""

import os
import sys

# 将项目根目录（scangate 的父目录）加入 sys.path，确保以脚本方式运行时也能 import scangate
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scangate.core.singleton import is_already_running, show_already_running
from scangate.ui.window import ScanGateApp


def main():
    if is_already_running():
        show_already_running()
        return
    # 关闭 PyInstaller 单文件启动闪屏（解压阶段显示，避免「无响应」观感）
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass
    app = ScanGateApp()
    app.mainloop()


if __name__ == "__main__":
    main()
