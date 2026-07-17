"""SCAN.GATE 打印机扫描共享工具 —— 应用配置层。

职责：
- 定义连接配置数据模型（ConnectionConfig）
- 负责配置的加载与持久化（JSON 文件）
- 不依赖任何 UI / 网络代码，保持纯净可单测
"""

import json
import os
import uuid
from dataclasses import dataclass, asdict, field

# ---------------- 应用元信息 ----------------
APP_NAME = "SCAN.GATE"
APP_TITLE = "SCAN.GATE · 打印机扫描共享工具"
VERSION = "4.2.0"
AUTHOR = "刘思元"
COPYRIGHT = "© 2026 刘思元. 版权所有"

# 关于窗口中点击作者名弹出的「公司内 / 公司外」链接
LINK_INTERNAL = "https://www.feishu.cn/invitation/page/add_contact/?token=9danc903-e18d-4e65-a6db-84f298eee4bf&unique_id=kwPuzpyzgwlmgKzs_R4Yrw=="
LINK_EXTERNAL = "https://www.feishu.cn/invitation/page/add_contact/?token=499l9235-d879-4aae-8998-705ab4102695&unique_id=8Ej7RorRZnSHTZXl2jcGUw=="

# 配置文件路径：沿用历史约定，放在用户主目录
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".printer_scan_config.json")


@dataclass
class ServerProfile:
    """一份完整的服务器连接配置（多档管理的基本单元）。"""

    id: str = ""
    name: str = "默认服务器"
    host: str = "192.168.4.82"
    share: str = "share"
    subfolder: str = "共享"
    username: str = "share"
    password: str = "share"

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]

    @property
    def unc_base(self) -> str:
        return f"\\\\{self.host}\\{self.share}"

    @property
    def root_path(self) -> str:
        return f"\\\\{self.host}\\{self.share}\\{self.subfolder}"

    @classmethod
    def from_dict(cls, d: dict) -> "ServerProfile":
        valid = {k: d.get(k, getattr(cls(), k)) for k in cls.__dataclass_fields__}
        return cls(**valid)


@dataclass
class ConnectionConfig:
    """网络连接配置（由当前生效的 ServerProfile 派生，保持旧调用兼容）。"""

    host: str = "192.168.4.82"
    share: str = "share"
    subfolder: str = "共享"
    username: str = "share"
    password: str = "share"

    @property
    def unc_base(self) -> str:
        return f"\\\\{self.host}\\{self.share}"

    @property
    def root_path(self) -> str:
        return f"\\\\{self.host}\\{self.share}\\{self.subfolder}"

    @classmethod
    def from_profile(cls, p: "ServerProfile") -> "ConnectionConfig":
        """由当前生效的 ServerProfile 派生出 ConnectionConfig（保持旧 UI 调用兼容）。"""
        return cls(
            host=p.host, share=p.share, subfolder=p.subfolder,
            username=p.username, password=p.password,
        )


class ConfigManager:
    """配置的读写管理器。

    - 新版格式：{ "servers": [ServerProfile...], "current_id": str }
    - 兼容旧版：若文件仅有扁平的 host/share/... 字段，则迁移为单档「默认服务器」
    - 读取失败 / 无档时静默回退到一份默认配置，绝不抛异常中断启动
    """

    def __init__(self, path: str | None = None):
        self.path = path or CONFIG_PATH
        self.servers: list = []
        self.current_id: str | None = None
        self.operator: str = ""        # 操作人姓名/备注（留空则自动用本机账号）
        self.load()

    def load(self) -> list:
        default = ServerProfile()
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
            if isinstance(data, dict) and "servers" in data and isinstance(data["servers"], list):
                self.servers = [ServerProfile.from_dict(s) for s in data["servers"]]
                self.current_id = data.get("current_id")
                self.operator = (data.get("operator") or "").strip()
            elif isinstance(data, dict):
                # 旧版扁平格式迁移
                flat = {k: data.get(k, getattr(default, k))
                        for k in ConnectionConfig.__dataclass_fields__}
                prof = ServerProfile(name="默认服务器", **flat)
                self.servers = [prof]
                self.current_id = prof.id
        if not self.servers:
            self.servers = [ServerProfile()]
            self.current_id = self.servers[0].id
        if self.current_id not in {s.id for s in self.servers}:
            self.current_id = self.servers[0].id
        return self.servers

    def active(self) -> ServerProfile:
        for s in self.servers:
            if s.id == self.current_id:
                return s
        return self.servers[0]

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "servers": [asdict(s) for s in self.servers],
                        "current_id": self.current_id,
                        "operator": self.operator,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass
