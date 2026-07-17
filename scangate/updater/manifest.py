"""版本清单探测与语义化版本比对。

fetch_manifest 遍历候选源（LAN 优先、Gitee 兜底），首个成功即返回：
- HTTP(S) 源：urllib 带超时读取 JSON
- 本地 / UNC(SMB) 路径：直接读文件

任何单源失败都被吞掉、继续尝试下一个；全部失败返回 (None, None)，
由上层决定「静默跳过」而绝不阻塞启动。
"""

import os
import re
import json
import time
import urllib.request

_NUM = re.compile(r"\d+")


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


def _read_source(src: str, timeout: int) -> str | None:
    """读取单个源的原始文本；失败返回 None（不抛异常）。"""
    try:
        if _is_http(src):
            req = urllib.request.Request(src, headers={"User-Agent": "SCAN.GATE-Updater"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return raw.decode("utf-8", errors="replace")
        else:
            # 本地 / UNC(SMB) 路径
            if not os.path.isfile(src):
                return None
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    except Exception:
        return None


def _validate(manifest: dict) -> bool:
    """清单最低合法性：必须有 version 与非空 files 列表，且每个 file 有 url。"""
    if not isinstance(manifest, dict):
        return False
    if "version" not in manifest:
        return False
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return False
    for f in files:
        if not isinstance(f, dict) or not f.get("url"):
            return False
    return True


def fetch_manifest(sources, timeout: int = 10, retries: int = 1):
    """按顺序探测候选源，返回 (manifest_dict, source_used)；全失败返回 (None, None)。

    - HTTP 源做 retries 次指数退避重试；本地路径重试意义不大，只试一次。
    - 只要有一个源成功且清单合法，立即返回，不再尝试后续源。
    """
    if not sources:
        return None, None
    for src in sources:
        attempts = retries if _is_http(src) else 1
        delay = 1.0
        for i in range(max(1, attempts)):
            text = _read_source(src, timeout)
            if text:
                try:
                    data = json.loads(text)
                except Exception:
                    data = None
                if _validate(data):
                    return data, src
            if i < attempts - 1:
                time.sleep(delay)
                delay *= 2
    return None, None


def pick_file(manifest: dict, target: str = "self") -> dict | None:
    """从清单 files 中挑出要替换的目标文件（默认 target=='self' 即主程序自身）。"""
    files = manifest.get("files") or []
    for f in files:
        if f.get("target", "self") == target:
            return f
    return files[0] if files else None
