"""在线更新子系统（双源回退：LAN 共享优先 + Gitee 公网兜底）。

模块划分：
- settings.py  更新源与偏好配置（内置默认 + 运行时覆盖文件，改源无需重新打包）
- manifest.py  语义化版本比对 + 多源清单探测
- download.py  Downloader：HTTP Range 续传 / SMB 分块续传 + SHA256 完整性校验
- install.py   备份 .bak + update.bat 接力，解决 onefile exe 无法原地替换自身
- rollback.py  启动自检与失败回滚
- updater.py   编排上述步骤的状态机 + 进度回调

设计原则：
- 检测失败绝不影响主程序启动（离线 / 超时静默跳过）。
- 版本比对 / 下载 / 校验 / 回滚为纯 Python，天然跨平台；仅「安装替换」按 OS 分派脚本。
- 双源对上层完全透明：只是把「单个清单地址」升级为「候选源列表」，首个成功即用。
"""

from .manifest import parse_version, compare_versions, is_newer, fetch_manifest
from .download import Downloader, sha256_of
from .settings import load_settings, save_settings, UpdateSettings
from .updater import Updater, UpdateState

__all__ = [
    "parse_version",
    "compare_versions",
    "is_newer",
    "fetch_manifest",
    "Downloader",
    "sha256_of",
    "load_settings",
    "save_settings",
    "UpdateSettings",
    "Updater",
    "UpdateState",
]
