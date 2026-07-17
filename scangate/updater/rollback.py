"""启动自检与回滚。

主程序启动、窗口成功创建后调用 mark_started()：写出「成功标记」，
让 update.bat 的轮询判定为「新版本启动成功」，从而删除 .bak、结束助手。

on_startup() 在程序早期调用，读取 pending.json 判断上次更新结果：
- 若存在 pending 且当前版本 == 目标版本 → 更新成功，清理状态并返回 ("success", 版本)
- 若存在 pending 但当前版本 != 目标版本 → 可能是回滚后的旧版启动，返回 ("rolledback", 目标版本)
- 无 pending → 正常启动，返回 ("normal", None)

真正的「崩溃即回滚」由 update.bat 的成功标记轮询兜底（见 install.py）；
本模块负责状态收尾与向用户反馈结果。
"""

import os
import json

from .install import FLAG_DIR, OK_FLAG, PENDING_FLAG


def mark_started() -> None:
    """新版本成功进入主循环时写出成功标记（供 bat 轮询）。"""
    try:
        os.makedirs(FLAG_DIR, exist_ok=True)
        with open(OK_FLAG, "w", encoding="utf-8") as f:
            f.write("ok")
    except Exception:
        pass


def _read_pending() -> dict | None:
    try:
        if not os.path.exists(PENDING_FLAG):
            return None
        with open(PENDING_FLAG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _clear_pending() -> None:
    for p in (PENDING_FLAG,):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def on_startup(current_version: str) -> tuple:
    """程序启动早期调用，返回 (result, info)。

    result ∈ {'normal','success','rolledback'}。
    """
    pending = _read_pending()
    if not pending:
        return ("normal", None)

    target = str(pending.get("new_version") or "")
    from .manifest import compare_versions

    if target and compare_versions(current_version, target) == 0:
        # 当前就是目标版本 → 更新成功
        _clear_pending()
        return ("success", target)

    # 当前不是目标版本：说明发生了回滚（bat 已还原 .bak 并重启旧版）
    _clear_pending()
    return ("rolledback", target)


def restore_backup() -> bool:
    """手动回滚：若存在 <exe>.bak，用其覆盖当前 exe（仅打包态有意义）。

    注意：运行中的 exe 被占用，通常无法原地覆盖，故此函数主要用于
    「下次由 bat 接力」的场景；此处提供接口供特殊维护调用。
    """
    import sys
    if not getattr(sys, "frozen", False):
        return False
    target = os.path.abspath(sys.executable)
    backup = target + ".bak"
    if not os.path.exists(backup):
        return False
    try:
        # 直接覆盖多半失败（占用），交由外部脚本处理；此处尽力尝试
        os.replace(backup, target)
        return True
    except Exception:
        return False
