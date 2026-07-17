"""更新源与偏好配置。

优先级（后者覆盖前者）：
1. 内置默认（DEFAULTS）
2. 打包内置的 update_source.json（随 exe 分发，发布方可预置）
3. 用户目录运行时覆盖 ~/.printer_scan_update.json（改源 / 改开关无需重新打包）

manifest_sources 为候选清单源列表，按顺序探测：
- Gitee API contents 端点（带 access_token 认证，绕过风控 403）
首个成功读取到的清单即采用。
"""

import os
import sys
import json
from dataclasses import dataclass, asdict, field

# 用户目录运行时覆盖文件（存在则覆盖内置源与偏好）
OVERRIDE_PATH = os.path.join(os.path.expanduser("~"), ".printer_scan_update.json")

# 内置默认：仅走 master 分支的「发行版（release）」作为更新源。
# 主源 = master 最新发行版（releases/latest，从 body 内嵌清单读取版本与说明）；
# 兜底源 = master 根目录 version.json（/contents/ API，小文件可靠）。
# 注：Gitee 对所有程序化下载直链（release 附件 / 源码包）返回 403，
# 因此更新采用「检测 + 通知 + 跳转发行版页面手动下载」模式，auto_install 关闭。
DEFAULTS = {
    "auto_check": True,
    "auto_install": False,
    "timeout": 30,
    "retries": 3,
    "manifest_sources": [
        "https://gitee.com/api/v5/repos/knightlsy/printer-scan-tool/releases/latest?access_token=08089ed69a061cc7cf7dc013348029a9",
        "https://gitee.com/api/v5/repos/knightlsy/printer-scan-tool/contents/version.json?ref=master&access_token=08089ed69a061cc7cf7dc013348029a9",
    ],
}


@dataclass
class UpdateSettings:
    auto_check: bool = True
    auto_install: bool = False
    timeout: int = 10
    retries: int = 3
    manifest_sources: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "UpdateSettings":
        base = dict(DEFAULTS)
        if isinstance(d, dict):
            base.update({k: v for k, v in d.items() if k in base})
        return cls(
            auto_check=bool(base["auto_check"]),
            auto_install=bool(base["auto_install"]),
            timeout=int(base["timeout"]),
            retries=int(base["retries"]),
            manifest_sources=list(base["manifest_sources"]),
        )


def _bundled_path() -> str:
    """打包内置的 update_source.json 路径（frozen 态在 _MEIPASS，开发态在包目录）。"""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "scangate", "updater", "update_source.json")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "update_source.json")


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_settings() -> UpdateSettings:
    """按优先级合并出最终生效的更新配置。"""
    merged = dict(DEFAULTS)
    # 2) 打包内置
    bundled = _read_json(_bundled_path())
    for k in merged:
        if k in bundled:
            merged[k] = bundled[k]
    # 3) 运行时覆盖
    override = _read_json(OVERRIDE_PATH)
    for k in merged:
        if k in override:
            merged[k] = override[k]
    return UpdateSettings.from_dict(merged)


def save_settings(settings: UpdateSettings) -> None:
    """把偏好写入运行时覆盖文件（仅持久化开关，不动源列表除非显式给出）。"""
    try:
        cur = _read_json(OVERRIDE_PATH)
        cur.update(asdict(settings))
        with open(OVERRIDE_PATH, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_prefs(auto_check: bool | None = None, auto_install: bool | None = None) -> UpdateSettings:
    """仅更新两个开关偏好并持久化，返回最新设置。"""
    s = load_settings()
    if auto_check is not None:
        s.auto_check = bool(auto_check)
    if auto_install is not None:
        s.auto_install = bool(auto_install)
    # 只写开关，避免把内置源覆盖进用户文件造成源固化
    try:
        cur = _read_json(OVERRIDE_PATH)
        cur["auto_check"] = s.auto_check
        cur["auto_install"] = s.auto_install
        with open(OVERRIDE_PATH, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return s
