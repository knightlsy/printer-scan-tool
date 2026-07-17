"""下载器：断点续传 + SHA256 完整性校验。

- Gitee API 源（/api/v5/repos/…/contents/）：通过认证 API 获取 base64 编码内容并解码写入
- HTTP(S) 源：优先用 Range 续传（服务器支持则从已落盘字节继续，返回 206；
  不支持 Range（返回 200）则从头重下）。
- 本地 / UNC(SMB) 源：分块复制，按已落盘偏移续传（等价「读偏移量继续」）。

下载写入 dest + '.part'，全部完成并通过 SHA256 校验后才原子 rename 为最终文件；
校验不通过则删除 .part，绝不产出半成品，是回滚机制的第一道保险。
"""

import os
import time
import json
import base64
import shutil
import hashlib
import urllib.request
import urllib.parse

_CHUNK = 1024 * 256  # 256KB


def _encode_url(url: str) -> str:
    """对 URL 的 path/query 做百分号编码，兼容含中文/空格的下载直链。

    仅编码非 ASCII 与空格等不安全字符，保留已编码部分（safe 覆盖常见分隔符）。
    """
    try:
        parts = urllib.parse.urlsplit(url)
        path = urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=~-._")
        query = urllib.parse.quote(parts.query, safe="=&%:@/?~-._")
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, path, query, parts.fragment)
        )
    except Exception:
        return url


def sha256_of(path: str, progress=None) -> str:
    """计算文件 SHA256（十六进制小写）。"""
    h = hashlib.sha256()
    size = os.path.getsize(path) if os.path.exists(path) else 0
    done = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress and size:
                progress(int(done / size * 100))
    return h.hexdigest()


def _is_http(url: str) -> bool:
    s = (url or "").lower()
    return s.startswith("http://") or s.startswith("https://")


def _is_gitee_api(url: str) -> bool:
    """判断是否为 Gitee API contents 端点。"""
    s = (url or "").lower()
    return "/api/v5/repos/" in s and "/contents/" in s


class DownloadError(Exception):
    pass


class Downloader:
    """把 url 下载到 dest，支持续传、进度回调、取消与 SHA256 校验。

    参数：
    - progress(pct, speed_bps): 进度回调（0-100 与瞬时速度字节/秒）
    - cancel(): 返回 True 则中断
    - expected_sha256 / expected_size: 用于校验（可为 None）
    """

    def __init__(self, url, dest, expected_sha256=None, expected_size=None,
                 progress=None, cancel=None, timeout=30, retries=3):
        self.url = url
        self.dest = dest
        self.part = dest + ".part"
        self.expected_sha256 = (expected_sha256 or "").lower().strip() or None
        self.expected_size = expected_size
        self.progress = progress or (lambda p, s: None)
        self.cancel = cancel or (lambda: False)
        self.timeout = timeout
        self.retries = retries

    # ---------------- 对外主流程 ----------------
    def run(self) -> str:
        """执行下载 + 校验，成功返回最终文件路径；失败抛 DownloadError。"""
        os.makedirs(os.path.dirname(os.path.abspath(self.dest)), exist_ok=True)
        last_err = None
        for attempt in range(max(1, self.retries)):
            try:
                if _is_gitee_api(self.url):
                    self._download_gitee_api()
                elif _is_http(self.url):
                    self._download_http()
                else:
                    self._copy_local()
                # 校验
                self._verify()
                # 原子落地
                if os.path.exists(self.dest):
                    os.remove(self.dest)
                os.replace(self.part, self.dest)
                return self.dest
            except _Cancelled:
                self._cleanup_part()
                raise DownloadError("已取消")
            except Exception as e:
                last_err = e
                # 校验失败：删掉 .part 从头重来；网络错误：保留 .part 下次续传
                if isinstance(e, _VerifyFailed):
                    self._cleanup_part()
                if attempt < self.retries - 1:
                    time.sleep(1.5 * (attempt + 1))
        raise DownloadError(str(last_err) if last_err else "下载失败")

    # ---------------- HTTP 续传 ----------------
    def _download_http(self) -> None:
        resume_from = os.path.getsize(self.part) if os.path.exists(self.part) else 0
        headers = {"User-Agent": "SCAN.GATE-Updater"}
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
        req = urllib.request.Request(_encode_url(self.url), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            # 服务器不支持 Range：返回 200，需从头写
            mode = "ab"
            if resume_from > 0 and status != 206:
                resume_from = 0
                mode = "wb"
            total = self._content_total(resp, resume_from, status)
            done = resume_from
            t0 = time.time()
            last_t, last_done = t0, done
            with open(self.part, mode) as f:
                while True:
                    if self.cancel():
                        raise _Cancelled()
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last_t >= 0.3:
                        speed = (done - last_done) / (now - last_t)
                        pct = int(done / total * 100) if total else 0
                        self.progress(min(pct, 100), speed)
                        last_t, last_done = now, done
            self.progress(100 if (total and done >= total) else 99, 0)

    # ---------------- Gitee API 下载（base64 解码） ----------------
    def _download_gitee_api(self) -> None:
        """通过 Gitee API contents 端点获取文件内容（base64 编码），解码后写入 .part。

        API 返回 JSON：{"content": "<base64>", "size": N, ...}
        不支持 Range 续传（API 每次返回完整内容），大文件会占用较多内存。
        """
        req = urllib.request.Request(
            _encode_url(self.url), headers={"User-Agent": "SCAN.GATE-Updater"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read()
        j = json.loads(raw)
        content_b64 = j.get("content", "")
        if not content_b64:
            raise DownloadError("Gitee API 返回空内容")
        data = base64.b64decode(content_b64)
        total = len(data)
        t0 = time.time()
        # 写入 .part（带进度）
        with open(self.part, "wb") as f:
            f.write(data)
        # 报告进度
        self.progress(100, total / max(time.time() - t0, 0.001))

    @staticmethod
    def _content_total(resp, resume_from, status) -> int:
        cl = resp.headers.get("Content-Length")
        try:
            length = int(cl) if cl is not None else 0
        except Exception:
            length = 0
        if status == 206:
            # 断点续传时 Content-Length 是剩余量
            return resume_from + length
        return length

    # ---------------- 本地 / SMB 分块续传 ----------------
    def _copy_local(self) -> None:
        if not os.path.isfile(self.url):
            raise FileNotFoundError(f"源文件不存在：{self.url}")
        total = os.path.getsize(self.url)
        resume_from = os.path.getsize(self.part) if os.path.exists(self.part) else 0
        # 若已落盘超过源大小（源被替换过），从头来
        if resume_from > total:
            resume_from = 0
        done = resume_from
        t0 = time.time()
        last_t, last_done = t0, done
        with open(self.url, "rb") as src, open(self.part, "ab" if resume_from else "wb") as dst:
            src.seek(resume_from)
            while True:
                if self.cancel():
                    raise _Cancelled()
                chunk = src.read(_CHUNK)
                if not chunk:
                    break
                dst.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last_t >= 0.3:
                    speed = (done - last_done) / (now - last_t)
                    pct = int(done / total * 100) if total else 0
                    self.progress(min(pct, 100), speed)
                    last_t, last_done = now, done
        self.progress(100, 0)

    # ---------------- 校验 ----------------
    def _verify(self) -> None:
        if not os.path.exists(self.part):
            raise _VerifyFailed("下载文件缺失")
        size = os.path.getsize(self.part)
        if self.expected_size and size != self.expected_size:
            raise _VerifyFailed(
                f"文件大小不符（期望 {self.expected_size}，实际 {size}）"
            )
        if self.expected_sha256:
            actual = sha256_of(self.part)
            if actual.lower() != self.expected_sha256:
                raise _VerifyFailed("SHA256 校验不通过（文件可能损坏或被篡改）")

    def _cleanup_part(self) -> None:
        try:
            if os.path.exists(self.part):
                os.remove(self.part)
        except Exception:
            pass


class _Cancelled(Exception):
    pass


class _VerifyFailed(Exception):
    pass
