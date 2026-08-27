"""连接会话审计记录器（跨双端复用的会话级审计）。

把「一次连接 → 断开」期间的多次文件操作（上传/下载/删除）汇总成一条
审计日志，断开/关闭时落盘。桌面端（customtkinter）与 Web 端（pywebview）
共用本类，保证两端审计行为完全一致，避免各写一套。

设计要点：
- begin() 建立会话（连接成功时调用）
- record() 记录单次操作（文件操作完成时调用）
- flush() 汇总落盘并上报 Worker（断开/关闭时调用，幂等）
- 所有写盘/上报异常都被吞掉：审计是「锦上添花」，绝不影响主业务流程
- 不依赖任何 UI / 网络细节，便于单测
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from scangate.services.auditlog import write_session_log


class SessionRecorder:
    """一次「连接 → 断开」会话的审计记录器。"""

    def __init__(self, operator: str = "", account: str = "",
                 app_version: str = "SCAN.GATE"):
        self.operator = operator
        self.account = account
        self.app_version = app_version
        self._session: Optional[dict] = None

    # ---------------- 生命周期 ----------------
    def begin(self, host: str, share: str, server_unc: str, subfolder: str) -> None:
        """连接成功时建立会话。若已有会话则先落盘旧的（防漏记）。"""
        self.flush()
        self._session = {
            "start": datetime.now(),
            "operator": self.operator,
            "account": self.account,
            "host": host,
            "share": share,
            "server_unc": server_unc,
            "subfolder": subfolder,
            "ops": [],
        }

    @property
    def active(self) -> bool:
        return self._session is not None

    def record(self, op_type: str, description: str, target: str = "",
               before_state: str = "", after_state: str = "",
               success: bool = True, reason: str = "", detail: str = "") -> None:
        """记录一次操作。会话未建立时静默忽略（保证可安全调用）。"""
        s = self._session
        if not s:
            return
        s["ops"].append({
            "time": datetime.now(),
            "op_type": op_type,
            "description": description,
            "target": target,
            "before_state": before_state,
            "after_state": after_state,
            "success": success,
            "reason": reason,
            "detail": detail,
        })

    def flush(self) -> None:
        """把当前会话汇总落盘并上报 Worker。幂等：无会话时什么都不做。"""
        s = self._session
        if not s:
            return
        self._session = None
        try:
            write_session_log(
                host=s["host"],
                share=s["share"],
                operator=s["operator"],
                account=s["account"],
                start_dt=s["start"],
                end_dt=datetime.now(),
                server_unc=s["server_unc"],
                subfolder=s["subfolder"],
                ops=s["ops"],
                app_version=self.app_version,
            )
        except Exception:
            pass
