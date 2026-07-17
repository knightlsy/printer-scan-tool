"""连接会话审计日志服务（后台执行，可被任意线程调用）。

设计要点：
- 【一次连接 → 一次断开 = 一条日志】。只要在与共享的连接会话期间做的所有文件操作
  （上传 / 下载 / 删除），都汇总进「该次会话」唯一的一个日志文件，落盘到共享根目录
  下的 `log` 子目录（默认即 `\\\\192.168.4.82\\share\\log`）。
- 日志目录 = `\\\\{host}\\{share}\\log`，由当前生效服务器的 host/share 推导。
- 若共享会话不可用（写日志那一刻已断开、或目录不可写），自动降级写到本机
  `~/.printer_scan_audit/<host>_<share>/` 备份目录，并在日志内标注「本地备份」，
  保证「任何会话都有据可查」，且绝不因写日志失败而中断主业务。
- 文件名 `log_<YYYYMMDD>_<HHMMSS>.log`（以连接开始时间为戳，精确到秒以避免重名）。
- 本模块完全自包含、不依赖 UI，便于单测。
"""

import os
import re
from datetime import datetime

# 本机备份根目录（共享不可写时的兜底落盘位置）
_LOCAL_AUDIT_ROOT = os.path.join(os.path.expanduser("~"), ".printer_scan_audit")

# 文件名非法字符清洗（Windows 不允许 \ / : * ? " < > |）
_INVALID = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _sanitize(name: str) -> str:
    s = _INVALID.sub("_", (name or "").strip())
    return s[:40] or "未知"


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "（未知）"


def _log_dir_for(host: str, share: str) -> str:
    return f"\\\\{host}\\{share}\\log"


def write_session_log(
    host: str,
    share: str,
    operator: str,
    account: str,
    start_dt: datetime,
    end_dt: datetime,
    server_unc: str,
    subfolder: str,
    ops: list,
    app_version: str = "",
) -> tuple[bool, str]:
    """把一次「连接 → 断开」会话汇成一条审计日志。

    ops: 会话内各操作的列表，每项含 time/op_type/description/target/
         before_state/after_state/success/reason/detail。
    返回 (是否写入共享目录, 实际落盘路径)。
    """
    who = _sanitize(operator or account or "未知操作人")
    # 文件名：log_<年月日>_<时分秒>.log，例如 log_20260101_120000.log
    fname = f"log_{start_dt.strftime('%Y%m%d_%H%M%S')}.log"
    # 每条日志条目的标识前缀：[用户名: 真实姓名]（真实姓名为空时不加）
    realname = (operator or "").strip()
    user_prefix = f"[用户名: {realname}] " if realname else ""

    lines = []
    lines.append("=" * 56)
    lines.append("SCAN.GATE 连接会话操作审计日志")
    lines.append("=" * 56)
    lines.append(f"连接时间：{_fmt(start_dt)}")
    lines.append(f"断开时间：{_fmt(end_dt)}")
    if operator:
        if account:
            lines.append(f"操作人  ：{operator}（账号：{account}）")
        else:
            lines.append(f"操作人  ：{operator}")
    else:
        lines.append(f"操作人  ：{account or '未知'}")
    lines.append(f"服务器  ：{server_unc} （子目录：{subfolder}）")
    lines.append(f"操作目录：{server_unc}\\{subfolder}")
    lines.append("-" * 56)
    lines.append(f"本会话共执行 {len(ops)} 项操作：")
    if not ops:
        lines.append("    （本会话未执行任何文件操作）")
    for i, op in enumerate(ops, 1):
        lines.append("-" * 56)
        lines.append(f"{user_prefix}[{i}] {_fmt(op.get('time'))}  {op.get('op_type', '操作')}")
        lines.append(f"    描述：{(op.get('description') or '').strip()}")
        if op.get("target"):
            lines.append(f"    对象：{op['target']}")
        lines.append(f"    操作前：{(op.get('before_state') or '（无）').strip()}")
        lines.append(f"    操作后：{(op.get('after_state') or '（无）').strip()}")
        lines.append(f"    结果：{'成功' if op.get('success', True) else '失败'}")
        if not op.get("success", True) and op.get("reason"):
            lines.append(f"    失败原因：{op['reason']}")
        if op.get("detail"):
            lines.append("    明细：")
            for d in op["detail"].split("\n"):
                lines.append("        " + d)
    lines.append("-" * 56)
    lines.append("溯源信息：")
    lines.append(f"    应用版本：{app_version or 'SCAN.GATE'}")
    lines.append(f"    服务器  ：{host} / 共享：{share}")
    if account:
        lines.append(f"    本机账号：{account}")
    lines.append("=" * 56)
    content = "\n".join(lines) + "\n"

    # 1) 优先写共享目录
    share_dir = _log_dir_for(host, share)
    try:
        os.makedirs(share_dir, exist_ok=True)
        path = os.path.join(share_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, path
    except Exception:
        pass

    # 2) 降级写本机备份
    try:
        local_dir = os.path.join(_LOCAL_AUDIT_ROOT, f"{_sanitize(host)}_{_sanitize(share)}")
        os.makedirs(local_dir, exist_ok=True)
        path = os.path.join(local_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write("【本地备份】本次因无法写入共享日志目录，已记录到本机备份。\n")
            f.write(content)
        return False, path
    except Exception:
        return False, ""
