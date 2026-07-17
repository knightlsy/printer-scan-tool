"""单实例守护。

使用 Windows 命名互斥体（Named Mutex）保证同一台机器上只运行一个实例。
- 首次运行：CreateMutexW 返回句柄，GetLastError() == 0
- 重复运行：互斥体已存在，GetLastError() == 183 (ERROR_ALREADY_EXISTS)
非 Windows 平台直接返回 False（不限制）。
"""

import sys
import ctypes

# 互斥体名称（全局唯一）
MUTEX_NAME = "SCAN_GATE_PRINTER_TOOL_INSTANCE_V3"

# 持有互斥体句柄，防止被 GC 回收导致互斥体提前释放
_INSTANCE_MUTEX = None


def is_already_running(name: str = MUTEX_NAME) -> bool:
    global _INSTANCE_MUTEX
    if not sys.platform.startswith("win"):
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        _INSTANCE_MUTEX = kernel32.CreateMutexW(None, 0, name)
        return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def show_already_running() -> None:
    try:
        ctk_user32 = ctypes.windll.user32
        ctk_user32.MessageBoxW(
            0,
            "SCAN.GATE 已在运行中，请勿重复打开。",
            "提示",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass
