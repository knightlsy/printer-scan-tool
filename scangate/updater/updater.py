"""更新编排器：把 检测 → 下载 → 校验 → 安装 串成状态机，并对外发进度回调。

上层（web/api.py）只需：
- Updater(current_version, on_event).check()  后台检测
- Updater(...).download_and_install(manifest)  下载并安装

on_event(event, payload) 是统一事件出口，payload 为 dict：
- ('checking', {})
- ('up_to_date', {'version': cur})
- ('found', {'version', 'notes', 'size', 'force', ...})
- ('error', {'message'})
- ('progress', {'stage', 'pct', 'speed'})   stage ∈ downloading/verifying/installing
- ('installing', {})
- ('ready', {'path'})            # 已下载校验完成，即将重启接力
- ('need_manual', {'path'})      # 开发态无法自替换，提示手动
"""

import os
import re
import tempfile

from .settings import load_settings
from .manifest import fetch_manifest, is_newer, pick_file
from .download import Downloader, DownloadError, download_via_chunks
from . import install as _install


def _parse_repo_token(sources):
    """从 manifest_sources 中解析首个 Gitee 源的 owner/repo 与 access_token。"""
    for s in (sources or []):
        m = re.search(r"/repos/([^/]+)/([^/]+)/releases/", s or "")
        if m:
            owner, repo = m.group(1), m.group(2)
            tm = re.search(r"access_token=([^&]+)", s or "")
            token = tm.group(1) if tm else ""
            return f"{owner}/{repo}", token
    return "", ""


class UpdateState:
    IDLE = "idle"
    CHECKING = "checking"
    FOUND = "found"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLING = "installing"
    ERROR = "error"


class Updater:
    def __init__(self, current_version: str, on_event=None, settings=None):
        self.current_version = current_version
        self.on_event = on_event or (lambda ev, payload: None)
        self.settings = settings or load_settings()
        self.state = UpdateState.IDLE
        self._latest = None       # 最近一次检测到的清单
        self._source = None

    def _emit(self, event: str, **payload):
        try:
            self.on_event(event, payload)
        except Exception:
            pass

    # ---------------- 检测 ----------------
    def check(self, silent: bool = False) -> dict | None:
        """探测候选源清单并与当前版本比对。

        返回：发现新版返回 manifest dict，否则 None。
        silent=True 时「已是最新」不发 up_to_date 事件（用于启动自检不打扰）。
        """
        self.state = UpdateState.CHECKING
        self._emit("checking")
        manifest, source, meta = fetch_manifest(
            self.settings.manifest_sources,
            timeout=self.settings.timeout,
            retries=self.settings.retries,
        )
        if not manifest:
            self.state = UpdateState.IDLE
            if not silent:
                self._emit("error", message="无法连接更新服务器（已跳过）")
            return None

        latest = manifest.get("version")
        if is_newer(latest, self.current_version):
            self._latest = manifest
            self._source = source
            self.state = UpdateState.FOUND
            f = pick_file(manifest) or {}
            # Gitee 对所有程序化下载直链返回 403，发行版网页（html_url）才是可人工下载的入口
            download_page = (meta or {}).get("html_url") or f.get("url") or ""
            self._emit(
                "found",
                version=latest,
                current=self.current_version,
                notes=manifest.get("notes", ""),
                size=f.get("size", 0),
                force=bool(manifest.get("force", False)),
                published_at=manifest.get("published_at", ""),
                source=source,
                download_page=download_page,
                download_url=f.get("url", ""),
                has_chunks=bool(f.get("chunks")),
            )
            return manifest

        self.state = UpdateState.IDLE
        if not silent:
            self._emit("up_to_date", version=self.current_version)
        return None

    # ---------------- 下载 + 安装 ----------------
    def _progress(self, pct, speed):
        self._emit("progress", stage="downloading", pct=pct, speed=speed)

    def _download_via_chunks(self, f: dict, version: str) -> str:
        """方案①：分块经 Gitee /contents/ API 下载并拼装为完整 exe，返回本地路径。"""
        repo, token = _parse_repo_token(self.settings.manifest_sources)
        if not repo or not token:
            raise DownloadError("缺少仓库/令牌配置，无法分块下载")
        name = f.get("name") or "update.exe"
        dest = os.path.join(tempfile.gettempdir(), f"scangate_update_{version}_{name}")
        return download_via_chunks(
            f["chunks"], repo, token, dest,
            expected_sha256=f.get("sha256"), expected_size=f.get("size"),
            progress=self._progress, cancel=lambda: False,
            timeout=max(30, self.settings.timeout), retries=self.settings.retries,
        )

    def download_and_install(self, manifest: dict | None = None, cancel=None) -> bool:
        """下载目标文件、校验并触发安装重启。成功进入安装流程返回 True。

        优先走分块方案（manifest file 含 chunks）：经 Gitee /contents/ API
        逐块下载 base64 解码拼装，绕过 403 与 10MB 限制，实现静默自动更新。
        """
        manifest = manifest or self._latest
        if not manifest:
            self._emit("error", message="没有可用的更新清单")
            return False
        f = pick_file(manifest)
        if not f:
            self._emit("error", message="更新清单缺少可下载文件")
            return False

        version = manifest.get("version", "")
        self.state = UpdateState.DOWNLOADING
        self._emit("progress", stage="downloading", pct=0, speed=0)

        dest = None
        try:
            if f.get("chunks"):
                # 方案①：分块经 Gitee /contents/ API 下载拼装
                dest = self._download_via_chunks(f, version)
            else:
                url = f.get("url")
                if not url:
                    self._emit("error", message="更新清单缺少下载地址（且无分块）")
                    return False
                name = f.get("name") or os.path.basename(url) or "update.exe"
                dest = os.path.join(tempfile.gettempdir(), f"scangate_update_{version}_{name}")
                dl = Downloader(
                    url, dest,
                    expected_sha256=f.get("sha256"), expected_size=f.get("size"),
                    progress=self._progress, cancel=cancel,
                    timeout=max(30, self.settings.timeout),
                    retries=self.settings.retries,
                )
                dl.run()
        except DownloadError as e:
            self.state = UpdateState.ERROR
            self._emit("error", message=f"下载失败：{e}")
            return False

        # 校验已在下载器内完成（sha256/size），到这里即视为完整
        self._emit("progress", stage="verifying", pct=100, speed=0)

        # 安装：备份 + 重启接力
        self.state = UpdateState.INSTALLING
        self._emit("installing")
        ok = _install.install_and_relaunch(dest, new_version=version)
        if not ok:
            # 开发态或非 frozen：无法自替换，提示手动
            self._emit("need_manual", path=dest, version=version)
            return False
        self._emit("ready", path=dest, version=version)
        return True
