"""版本清单探测与语义化版本比对。

fetch_manifest 遍历候选源，首个成功即返回 (manifest, source, meta)：
- Gitee 发行版源（/api/v5/repos/…/releases/…）：读取 release 对象，
  从 body 中抽取内嵌的 ```scangate-manifest 代码块作为清单（结构化、可靠）；
  附带 meta = {html_url, tag_name} 供前端跳转发行版页面。
- Gitee API contents 源（/api/v5/repos/…/contents/）：自动识别 JSON 响应并 base64 解码内容
  （仅适合小文件，如 master 根目录的 version.json 兜底清单）。
- 普通 HTTP(S) 源：urllib 带超时读取文本
- 本地 / UNC(SMB) 路径：直接读文件

任何单源失败都被吞掉、继续尝试下一个；全部失败返回 (None, None, None)，
由上层决定「静默跳过」而绝不阻塞启动。
"""

import os
import re
import json
import time
import base64
import urllib.request

_NUM = re.compile(r"\d+")
# 从 release body 抽取内嵌清单：```scangate-manifest\n{...}\n```
_EMBED = re.compile(r"```scangate-manifest\s*\n(.*?)```", re.DOTALL)


def parse_version(v) -> tuple:
    """把 '4.2.0' / 'v4.2.0-beta' 解析为可比较的整数元组 (4,2,0)。

    - 容忍前缀 'v'、后缀预发布标签；只取点分数字段。
    - 非法/空值返回 (0,)，保证比较不抛异常。
    """
    if v is None:
        return (0,)
    s = str(v).strip().lstrip("vV")
    parts = []
    for seg in s.split("."):
        m = _NUM.search(seg)
        if m:
            parts.append(int(m.group()))
        else:
            break
    return tuple(parts) if parts else (0,)


def compare_versions(a, b) -> int:
    """比较两版本：a>b 返回 1，a<b 返回 -1，相等返回 0（按元组逐位、短的补零）。"""
    ta, tb = parse_version(a), parse_version(b)
    n = max(len(ta), len(tb))
    ta = ta + (0,) * (n - len(ta))
    tb = tb + (0,) * (n - len(tb))
    if ta > tb:
        return 1
    if ta < tb:
        return -1
    return 0


def is_newer(latest, current) -> bool:
    """latest 是否严格新于 current。"""
    return compare_versions(latest, current) > 0


def _is_http(src: str) -> bool:
    s = (src or "").lower()
    return s.startswith("http://") or s.startswith("https://")


def _is_gitee_api_contents(src: str) -> bool:
    """Gitee API contents 端点（返回 base64 编码的 JSON，仅适合小文件）。"""
    s = (src or "").lower()
    return "/api/v5/repos/" in s and "/contents/" in s


def _is_gitee_release(src: str) -> bool:
    """Gitee 发行版（release）API 端点：/api/v5/repos/…/releases/…"""
    s = (src or "").lower()
    return "/api/v5/repos/" in s and "/releases/" in s and "/contents/" not in s


def _read_gitee_release(src: str, timeout: int):
    """读取 Gitee 发行版源，返回 (manifest_text, meta)。失败返回 (None, None)。

    - 拉取 release 对象（支持 /releases/latest 或 /releases/{id} 或 /releases/tags/{tag}）
    - 从 body 抽取 ```scangate-manifest 内嵌块作为结构化清单
    - meta 携带 html_url（发行版网页）供前端跳转；
      Gitee API 不返回 html_url 字段，故从源 URL 解析 owner/repo 并拼出
      https://gitee.com/{owner}/{repo}/releases/tag/{tag} 作为人工下载入口。
    """
    try:
        req = urllib.request.Request(src, headers={"User-Agent": "SCAN.GATE-Updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        rel = json.loads(raw)
        if not isinstance(rel, dict):
            return None, None
        body = rel.get("body") or ""
        m = _EMBED.search(body)
        text = m.group(1).strip() if m else None
        if not text:
            return None, None
        tag = rel.get("tag_name") or ""
        # 从源 URL 解析 owner/repo：/repos/{owner}/{repo}/releases/...
        mrepo = re.search(r"/repos/([^/]+)/([^/]+)/releases/", src)
        owner = mrepo.group(1) if mrepo else ""
        repo = mrepo.group(2) if mrepo else ""
        page = f"https://gitee.com/{owner}/{repo}/releases/tag/{tag}" if (owner and repo and tag) else (rel.get("html_url") or "")
        meta = {
            "html_url": page,
            "tag_name": tag,
            "target_commitish": rel.get("target_commitish") or "",
        }
        return text, meta
    except Exception:
        return None, None


def _read_source(src: str, timeout: int):
    """读取单个源的原始文本；失败返回 (None, None)。

    - Gitee 发行版源：抽取内嵌清单文本
    - Gitee API contents 源：自动检测 JSON 响应并 base64 解码 content 字段
    - 普通 HTTP(S)：直接读取响应体
    - 本地/UNC：读文件
    返回 (text, meta)；meta 仅 Gitee 发行版源有内容。
    """
    try:
        if _is_gitee_release(src):
            return _read_gitee_release(src, timeout)
        if _is_http(src):
            req = urllib.request.Request(src, headers={"User-Agent": "SCAN.GATE-Updater"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            if _is_gitee_api_contents(src):
                try:
                    j = json.loads(raw)
                    if isinstance(j, dict) and "content" in j:
                        return base64.b64decode(j["content"]).decode("utf-8", errors="replace"), None
                except Exception:
                    pass
            return raw.decode("utf-8", errors="replace"), None
        else:
            if not os.path.isfile(src):
                return None, None
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                return f.read(), None
    except Exception:
        return None, None


def _validate(manifest: dict) -> bool:
    """清单最低合法性：必须有 version 与非空 files 列表，且每个 file 有下载地址。

    下载地址可以是单条 url（兼容旧清单），也可以是 urls 候选列表
    （jsDelivr 加速直链优先 + ghproxy/raw 兜底），二选一即可。
    """
    if not isinstance(manifest, dict):
        return False
    if "version" not in manifest:
        return False
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return False
    for f in files:
        if not isinstance(f, dict):
            return False
        has_addr = bool(f.get("url")) or (
            isinstance(f.get("urls"), list) and any(f.get("urls"))
        )
        if not (has_addr or f.get("chunks")):
            return False
    return True


def fetch_manifest(sources, timeout: int = 10, retries: int = 1):
    """按顺序探测候选源，返回 (manifest_dict, source_used, meta)；全失败返回 (None, None, None)。

    - HTTP 源做 retries 次指数退避重试；本地路径重试意义不大，只试一次。
    - 只要有一个源成功且清单合法，立即返回，不再尝试后续源。
    - meta 为发行版附加信息（html_url 等），非发行版源为 None。
    """
    if not sources:
        return None, None, None
    for src in sources:
        attempts = retries if (_is_http(src) and not _is_gitee_release(src)) else 1
        delay = 1.0
        for i in range(max(1, attempts)):
            text, meta = _read_source(src, timeout)
            if text:
                try:
                    data = json.loads(text)
                except Exception:
                    data = None
                if _validate(data):
                    return data, src, meta
            if i < attempts - 1:
                time.sleep(delay)
                delay *= 2
    return None, None, None


def pick_file(manifest: dict, target: str = "self") -> dict | None:
    """从清单 files 中挑出要替换的目标文件（默认 target=='self' 即主程序自身）。"""
    files = manifest.get("files") or []
    for f in files:
        if f.get("target", "self") == target:
            return f
    return files[0] if files else None
