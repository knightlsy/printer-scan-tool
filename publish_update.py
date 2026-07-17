#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键发布到 Gitee：源码推 master + 在 master 上建/更新发行版（release）。

用法：
    python publish_update.py --exe dist/打印机扫描工具_v4.exe --version 4.3.0 \
        --notes "更新机制支持分块自动下载安装"

做了什么：
1. 计算 exe 的 SHA256 与大小；
2. 将 exe 按 <7MB 分块（base64 后约 9.3MB，规避 Gitee /contents/ 的 10MB 限制），
   经 /contents/ API 上传到 master 的 update_chunks/{version}/ 目录；
3. 生成 version.json（结构化清单，含 chunks 元信息）写入仓库根目录；
4. git add + commit + push 到 master（源码随版本入库，发行版自动生成源码包）；
5. 在 master 上建/更新语义化发行版（tag=版本号），release body 内嵌
   ```scangate-manifest 清单块（含 chunks），供客户端分块自动下载拼装；
6. 将 exe 作为发行版附件上传（人工从页面下载的兜底，Gitee 禁止程序化下载附件）。

客户端行为：检测到新版本且清单含 chunks 时，自动经 /contents/ API 逐块下载、
SHA256 拼装校验、替换重启，实现静默自动更新（方案①）。
"""

import os
import sys
import json
import base64
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.error

TOKEN = "08089ed69a061cc7cf7dc013348029a9"
GITEE_REPO = "knightlsy/printer-scan-tool"
OWNER, REPO = GITEE_REPO.split("/")
UA = {"User-Agent": "SCAN.GATE-Publisher"}
API = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}"

CHUNK_RAW = 7 * 1024 * 1024   # 7MB 原始分块（base64 后约 9.3MB < 10MB 上限）


# ---------------- git ----------------
def git(*args, check=True):
    cmd = ["git", *args]
    print("  $ git", " ".join(args))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("  [git stderr]", r.stderr.strip() or r.stdout.strip())
        raise RuntimeError(f"git {' '.join(args)} 失败")
    return r


def push_master(version: str) -> None:
    origin = f"https://{OWNER}:{TOKEN}@gitee.com/{GITEE_REPO}.git"
    git("add", "-A")
    st = git("status", "--porcelain", check=False)
    if not st.stdout.strip():
        print("  [git] 无改动，跳过 commit")
        return
    git("commit", "-m", f"release v{version}")
    git("push", origin, "master")


# ---------------- 计算哈希 ----------------
def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------- Gitee API ----------------
def api(method, path, data=None, headers=None, raw=False):
    url = f"{API}{path}?access_token={TOKEN}"
    if isinstance(data, dict):
        payload = json.dumps(data).encode("utf-8")
        h = {"Content-Type": "application/json", **UA}
    else:
        payload = data
        h = dict(headers or UA)
    req = urllib.request.Request(url, data=payload, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, (r.read() if raw else r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def put_content(path, content_b64, message):
    """PUT/POST 写入仓库文件（base64）。已存在则带 sha 覆盖，支持重发同版本。"""
    st, b = api("GET", f"/contents/{path}")
    sha = None
    if st < 300:
        try:
            sha = json.loads(b).get("sha")
        except Exception:
            sha = None
    payload = {"message": message, "content": content_b64, "branch": "master"}
    if sha:
        payload["sha"] = sha
        verb = "PUT"
    else:
        verb = "POST"
    st, b = api(verb, f"/contents/{path}", payload)
    if st < 300:
        return True
    # POST 因已存在失败（422），补 GET sha 再 PUT
    if st == 422 and not sha:
        st2, b2 = api("GET", f"/contents/{path}")
        if st2 < 300:
            sha2 = json.loads(b2).get("sha")
            st3, b3 = api("PUT", f"/contents/{path}", {**payload, "sha": sha2})
            if st3 < 300:
                return True
            raise RuntimeError(f"分块覆盖失败 {path} {st3}: {b3[:120]}")
    raise RuntimeError(f"分块写入失败 {path} {st}: {b[:120]}")


def upload_chunks(exe_path, version):
    """将 exe 按 CHUNK_RAW 分块上传到 update_chunks/{version}/，返回 parts 元信息。"""
    base = f"update_chunks/{version}"
    parts = []
    idx = 0
    with open(exe_path, "rb") as f:
        while True:
            data = f.read(CHUNK_RAW)
            if not data:
                break
            name = f"part_{idx:03d}.bin"
            b64 = base64.b64encode(data).decode("ascii")
            put_content(f"{base}/{name}", b64, f"chunk {name} for v{version}")
            parts.append({
                "name": name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
            print(f"  [ok] 分块 {name} ({len(data)} B)")
            idx += 1
    return {"base_path": base, "count": len(parts), "chunk_raw": CHUNK_RAW, "parts": parts}


def find_release_by_tag(tag: str):
    st, body = api("GET", f"/releases/tags/{tag}")
    if st < 300:
        return json.loads(body)
    return None


def ensure_release(tag: str, name: str, body: str) -> dict:
    existing = find_release_by_tag(tag)
    if existing:
        st, b = api("PATCH", f"/releases/{existing['id']}",
                    {"tag_name": tag, "name": name, "body": body,
                     "target_commitish": "master"})
        if st < 300:
            return json.loads(b)
        print("  [warn] PATCH 失败：", b[:160])
    st, b = api("POST", "/releases",
                {"tag_name": tag, "name": name, "body": body,
                 "target_commitish": "master"})
    if st < 300:
        return json.loads(b)
    raise RuntimeError(f"创建发行版失败 {st}: {b[:200]}")


def upload_asset(release_id: int, exe_path: str) -> bool:
    """上传 exe 为发行版附件（尽力而为，人工下载兜底）。"""
    name = os.path.basename(exe_path)
    boundary = "----SCANGATE_BOUNDARY"
    with open(exe_path, "rb") as f:
        filedata = f.read()
    mp = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + filedata + f"\r\n--{boundary}--\r\n".encode("utf-8")
    h = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    st, b = api("POST", f"/releases/{release_id}/attach_files", data=mp, headers=h)
    if st < 300:
        print(f"  [ok] 已上传附件 {name}")
        return True
    print(f"  [warn] 附件上传失败 {st}: {b[:160]}（不影响版本发布，可稍后在页面手动上传）")
    return False


# ---------------- 清单 ----------------
def build_manifest(exe_path, version, notes, min_version, force, chunks) -> dict:
    name = os.path.basename(exe_path)
    size = os.path.getsize(exe_path)
    digest = sha256_of(exe_path)
    now = __import__("datetime").datetime.now(
        __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))
    ).isoformat()
    return {
        "version": version,
        "channel": "stable",
        "published_at": now,
        "notes": notes,
        "min_version": min_version or "",
        "force": bool(force),
        "files": [{
            "name": name,
            "size": size,
            "sha256": digest,
            "target": "self",
            "chunks": chunks,
        }],
    }


def main():
    ap = argparse.ArgumentParser(description="发布 SCAN.GATE 更新到 Gitee（master + 发行版，分块上传）")
    ap.add_argument("--exe", required=True, help="要发布的 exe 路径")
    ap.add_argument("--version", required=True, help="版本号，如 4.3.0")
    ap.add_argument("--notes", default="", help="更新说明（markdown）")
    ap.add_argument("--min-version", default="", help="强制更新的最低版本（可空）")
    ap.add_argument("--force", action="store_true", help="强制所有旧版更新")
    ap.add_argument("--no-git", action="store_true", help="跳过 git 推送到 master")
    ap.add_argument("--no-asset", action="store_true", help="不上传 exe 附件")
    ap.add_argument("--no-chunks", action="store_true", help="不分块上传（仅发清单，走前往下载）")
    args = ap.parse_args()

    if not os.path.isfile(args.exe):
        print(f"错误：找不到 exe：{args.exe}")
        sys.exit(1)

    version = args.version
    print(f"[1/5] 生成清单（exe={os.path.basename(args.exe)}）")
    if args.no_chunks:
        chunks = None
        print("      跳过分块上传（--no-chunks）")
    else:
        print(f"      分块上传 exe -> update_chunks/{version}/")
        chunks = upload_chunks(args.exe, version)
    manifest = build_manifest(args.exe, version, args.notes, args.min_version, args.force, chunks)
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)

    root_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    with open(root_json, "w", encoding="utf-8") as f:
        f.write(manifest_json)
    print(f"      version.json 已写入 {root_json}")

    body = f"{args.notes}\n\n```scangate-manifest\n{manifest_json}\n```\n"

    if not args.no_git:
        print(f"[2/5] 推送源码到 master（v{version}）")
        push_master(version)
    else:
        print(f"[2/5] 跳过 git 推送（--no-git）")

    print(f"[3/5] 建/更新 master 发行版 v{version}")
    rel = ensure_release(version, version, body)
    rid = rel.get("id")
    html_url = rel.get("html_url")
    print(f"      发行版：{html_url}")

    if not args.no_asset and rid:
        print(f"[4/5] 上传 exe 附件（人工下载兜底）")
        upload_asset(rid, args.exe)
    else:
        print(f"[4/5] 跳过附件上传")

    print(f"[5/5] 完成")
    print("\n=== 完成 ===")
    print(f"版本：v{version}")
    print(f"发行版：{html_url}")
    if chunks:
        print(f"分块数：{chunks['count']}（客户端将自动分块下载拼装安装）")
    else:
        print("客户端下次启动将检测到该版本并提示前往发行版页面下载。")


if __name__ == "__main__":
    main()
