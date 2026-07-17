"""网络连接服务（后台执行）。

通过 Windows `net use` 建立到 SMB 共享的会话，随后以 UNC 路径直接访问子目录。
关键改进：
- 所有调用都在后台线程执行（由 WorkerPool 调度），主线程不阻塞。
- `_run()` 用 0.5s 轮询 + 取消令牌实现「超时」与「用户取消」双重保护，
  即使共享无响应，UI 也始终可操作（显示进度遮罩 + 取消按钮）。
"""

import os
import subprocess
import sys
from typing import Callable

from scangate.config import ConnectionConfig

# Windows 下隐藏子进程控制台窗口，避免闪框
CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0

# 默认连接超时（秒）
CONNECT_TIMEOUT = 25
DISCONNECT_TIMEOUT = 15

# Windows net use / SMB 常见错误码 → 友好提示
_WIN_ERROR_MAP: dict[int, str] = {
    5: "访问被拒绝，请检查账号权限",
    53: "找不到网络路径，请检查服务器地址是否正确",
    67: "找不到网络名，请检查共享文件夹名称",
    85: "本地设备名已被使用",
    86: "密码错误",
    121: "会话超时或已断开",
    1219: "账号或密码错误，或存在冲突的连接会话（可尝试重启工具）",
    1326: "登录失败：用户名或密码不正确",
    1327: "账户限制（如密码过期、不允许登录时段）",
    1904: "无法在指定服务器上完成登录操作",
    2242: "密码已过期，请先修改密码后重试",
}


def _run(cmd: list[str], timeout: float = 20, cancel=None) -> str:
    """执行命令，支持超时与取消。返回 stdout。非零退出码抛 ConnectionError。"""
    kw = {}
    if CREATE_NO_WINDOW:
        kw["creationflags"] = CREATE_NO_WINDOW
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="gbk",
        errors="replace",
        **kw,
    )
    elapsed = 0.0
    while True:
        if cancel is not None and cancel.is_cancelled():
            proc.kill()
            raise InterruptedError("已取消")
        try:
            out, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            elapsed += 0.5
            if elapsed >= timeout:
                proc.kill()
                out, err = proc.communicate()
                raise TimeoutError(f"操作超时（{int(timeout)}秒），请检查网络或服务器地址")
    if proc.returncode != 0:
        code = proc.returncode
        # 优先用已知错误码映射表给出可读提示
        hint = _WIN_ERROR_MAP.get(code)
        if hint:
            raise ConnectionError(hint)
        # 未知错误码：显示解码后的原始信息（GBK 已正确解码）
        msg = (err or out or "").strip()
        raise ConnectionError(f"连接失败(代码{code}): {msg}")
    return out


def connect(
    progress: Callable, cancel, cfg: ConnectionConfig
) -> bool:
    """建立共享会话并验证子目录可访问。"""
    progress(10, "正在建立连接…")
    target = f"\\\\{cfg.host}\\{cfg.share}"
    try:
        _run(
            ["net", "use", target, f"/user:{cfg.username}", cfg.password],
            timeout=CONNECT_TIMEOUT,
            cancel=cancel,
        )
    except Exception:
        # 可能已存在会话，先尝试断开再连
        try:
            _run(["net", "use", target, "/delete", "/y"], timeout=DISCONNECT_TIMEOUT, cancel=cancel)
        except Exception:
            pass
        _run(
            ["net", "use", target, f"/user:{cfg.username}", cfg.password],
            timeout=CONNECT_TIMEOUT,
            cancel=cancel,
        )
    progress(60, "验证目录可访问…")
    if not os.path.isdir(cfg.root_path):
        raise FileNotFoundError(f"无法访问目录: {cfg.root_path}\n请确认服务器/共享名/子目录是否正确")
    progress(100, "已连接")
    return True


def disconnect(
    progress: Callable, cancel, cfg: ConnectionConfig
) -> bool:
    """断开共享会话（尽力而为，失败不抛异常）。"""
    target = f"\\\\{cfg.host}\\{cfg.share}"
    try:
        _run(["net", "use", target, "/delete", "/y"], timeout=DISCONNECT_TIMEOUT, cancel=cancel)
    except Exception:
        pass
    if progress:
        progress(100, "已断开")
    return True
