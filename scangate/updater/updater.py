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
    """（保留兼容）未使用：GitHub 模式无需 token，清单直链匿名下载。"""
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
            # 主下载地址（优先 CDN 加速直链），用于界面展示 / 手动下载入口
            urls = f.get("urls") or ([f.get("url")] if f.get("url") else [])
            download_page = (meta or {}).get("html_url") or urls[0] or ""
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
                download_url=urls[0] if urls else (f.get("url") or ""),
                download_urls=urls,
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

    def download_and_install(self, manifest: dict | None = None, cancel=None) -> bool:
        """下载目标文件、校验并触发安装重启。成功进入安装流程返回 True。

        CDN 加速方案：清单 file 提供 urls 候选列表（jsDelivr 加速直链优先，
        其后为 ghproxy 镜像 / raw.githubusercontent 直链兜底）。按顺序逐个尝试，
        首个成功（断点续传 + SHA256 校验通过）即采用，实现「高速 + 稳定」的
        静默全自动更新；某镜像失败时自动清理残片并切到下一个，绝不中断升级。
        """
        manifest = manifest or self._latest
        if not manifest:
            self._emit("error", message="没有可用的更新清单")
            return False
        f = pick_file(manifest)
        if not f:
            self._emit("error", message="更新清单缺少可下载文件")
            return False
        urls = f.get("urls") or ([f.get("url")] if f.get("url") else [])
        if not urls:
            self._emit("error", message="更新清单缺少下载地址（请检查发布配置）")
            return False

        version = manifest.get("version", "")
        name = f.get("name") or os.path.basename(urls[0]) or "update.exe"
        self.state = UpdateState.DOWNLOADING
        self._emit("progress", stage="downloading", pct=0, speed=0)
        dest = os.path.join(tempfile.gettempdir(), f"scangate_update_{version}_{name}")

        last_err = None
        for idx, attempt_url in enumerate(urls):
            if idx > 0:
                # 切到备用镜像：重置进度条，避免沿用上一个镜像的进度
                self._emit("progress", stage="downloading", pct=0, speed=0)
            try:
                dl = Downloader(
                    attempt_url, dest,
                    expected_sha256=f.get("sha256"), expected_size=f.get("size"),
                    progress=self._progress, cancel=cancel,
                    timeout=max(30, self.settings.timeout),
                    retries=self.settings.retries,
                )
                dl.run()
                last_err = None
                break
            except DownloadError as e:
                last_err = e
                # 清理上一条镜像残留的 .part，防止下一个镜像误续传到损坏内容
                try:
                    part = dest + ".part"
                    if os.path.exists(part):
                        os.remove(part)
                except Exception:
                    pass
                continue
        if last_err is not None:
            self.state = UpdateState.ERROR
            self._emit("error", message=f"下载失败（已尝试全部镜像）：{last_err}")
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
