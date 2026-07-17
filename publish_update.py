#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键发布到 GitHub：建仓库 + 源码推 master + 建 release + 上传 exe asset。

用法：
    python publish_update.py --exe dist/打印机扫描工具_v4.exe --version 4.5.0 \
        --notes "更新说明" --token ghp_xxx

做了什么：
1. 若仓库不存在则经 API 新建公开仓库（默认分支 master）；
2. 在 master 上建/更新发行版（tag=版本号）；
3. 将 exe 作为发行版 asset 上传，并采用 GitHub 返回的真实 browser_download_url
   （避免中文文件名拼接出错）；
4. 生成 version.json（结构化清单，files[0].url = 上述真实直链）写入仓库根目录；
5. git push 源码到 GitHub master（version.json 即客户端清单源，
   raw.githubusercontent.com/{owner}/{repo}/master/version.json 匿名可读、无 403）。

客户端从 version.json 拿到直链后直接断点续传下载，无 403、无需 token，
实现静默全自动更新。

注：GitHub 下载直链形如
    https://github.com/{owner}/{repo}/releases/download/{tag}/{file}
对程序化请求返回 200（与 Gitee 不同），是方案 C 的核心优势。
token 仅经 --token / 环境变量 GITHUB_TOKEN 传入，绝不写入任何仓库文件。
"""

import os
import sys
import json
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.error
import urllib.parse

MASK = "***"


def _mask(token: str, s: str) -> str:
    if token and token in s:
        return s.replace(token, MASK)
    return s


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


# ---------------- git ----------------
def git(*args, check=True, token=""):
    shown = [_mask(token, a) if isinstance(a, str) else a for a in args]
    print("  $ git", " ".join(shown))
    cmd = ["git", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout).strip()
        print("  [git stderr]", _mask(token, err))
        raise RuntimeError(f"git {shown} 失败")
    return r


def push_master(version: str, token: str, repo: str) -> None:
    origin = f"https://x-access-token:{token}@github.com/{repo}.git"
    git("add", "-A")
    st = git("status", "--porcelain", check=False)
    if not st.stdout.strip():
        print("  [git] 无改动，跳过 commit")
        return
    git("commit", "-m", f"release v{version}")
    try:
        git("push", origin, "master")
    except RuntimeError:
        # 远程有更新时自动 rebase 再推
        print("  [git] push 被拒，fetch + rebase 后重试")
        git("fetch", origin, "master")
        git("rebase", "FETCH_HEAD")
        git("push", origin, "master")


# ---------------- GitHub API ----------------
def gh_api(method, url, data=None, headers=None, raw=False, token=""):
    if isinstance(data, dict):
        payload = json.dumps(data).encode("utf-8")
        h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}",
             "User-Agent": "SCAN.GATE-Publisher"}
    else:
        payload = data
        h = dict(headers or {
            "Authorization": f"Bearer {token}",
            "User-Agent": "SCAN.GATE-Publisher",
        })
    req = urllib.request.Request(url, data=payload, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, (r.read() if raw else r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def create_repo_if_needed(token, owner, name, description):
    """若仓库不存在则新建公开仓库；返回 ('created'|'exists'|'error', msg)。"""
    api = "https://api.github.com"
    st, b = gh_api("GET", f"{api}/repos/{owner}/{name}", token=token)
    if st < 300:
        print(f"  [repo] 已存在 {owner}/{name}")
        return "exists", ""
    # 404 -> 新建
    st2, b2 = gh_api("POST", f"{api}/user/repos",
                     {"name": name, "private": False,
                      "description": description or "",
                      "auto_init": False, "has_issues": True},
                     token=token)
    if st2 < 300:
        print(f"  [repo] 已新建 {owner}/{name}")
        return "created", ""
    print(f"  [repo] 新建失败 {st2}: {b2[:200]}")
    return "error", b2


def set_default_branch(token, api_base, branch="master"):
    st, b = gh_api("PATCH", api_base,
                   {"name": api_base.rstrip('/').split('/')[-1], "default_branch": branch},
                   token=token)
    if st < 300:
        print(f"  [repo] 默认分支已设为 {branch}")
    else:
        print(f"  [warn] 设置默认分支失败 {st}: {b[:160]}")


def ensure_release(tag, name, notes, token, api_base):
    # 已存在则 PATCH，否则 POST
    st, b = gh_api("GET", f"{api_base}/releases/tags/{tag}", token=token)
    if st < 300:
        rid = json.loads(b)["id"]
        st2, b2 = gh_api("PATCH", f"{api_base}/releases/{rid}",
                         {"tag_name": tag, "name": name, "body": notes}, token=token)
        if st2 < 300:
            return json.loads(b2)
        print("  [warn] PATCH 失败：", b2[:160])
    st, b = gh_api("POST", f"{api_base}/releases",
                   {"tag_name": tag, "name": name, "body": notes,
                    "draft": False, "prerelease": False}, token=token)
    if st < 300:
        return json.loads(b)
    raise RuntimeError(f"创建发行版失败 {st}: {b[:200]}")


def upload_asset(release_id, exe_path, name, token, upload_base):
    """上传 exe 附件，成功返回 GitHub 真实 browser_download_url，否则 None。"""
    url = f"{upload_base}/releases/{release_id}/assets?name={urllib.parse.quote(name)}"
    with open(exe_path, "rb") as f:
        data = f.read()
    st, b = gh_api("POST", url, data,
                   headers={"Content-Type": "application/octet-stream"}, token=token)
    if st < 300:
        try:
            j = json.loads(b)
            dl = j.get("browser_download_url")
            print(f"  [ok] 已上传附件 {name} ({len(data)} B) -> {dl}")
            return dl
        except Exception:
            pass
        print(f"  [ok] 已上传附件 {name} ({len(data)} B)")
        return None
    print(f"  [warn] 附件上传失败 {st}: {b[:160]}")
    return None


def build_manifest(exe_path, version, notes, min_version, force, owner, repo,
                   download_url=None) -> dict:
    name = os.path.basename(exe_path)
    size = os.path.getsize(exe_path)
    digest = sha256_of(exe_path)
    if not download_url:
        download_url = (f"https://github.com/{owner}/{repo}/releases/download/"
                        f"{version}/{urllib.parse.quote(name)}")
    return {
        "version": version,
        "channel": "stable",
        "published_at": now_iso(),
        "notes": notes,
        "min_version": min_version or "",
        "force": bool(force),
        "files": [{
            "name": name,
            "size": size,
            "sha256": digest,
            "target": "self",
            "url": download_url,
        }],
    }


def main():
    ap = argparse.ArgumentParser(description="发布 SCAN.GATE 更新到 GitHub（建仓库 + master + 发行版，匿名直链下载）")
    ap.add_argument("--exe", required=True, help="要发布的 exe 路径")
    ap.add_argument("--version", required=True, help="版本号，如 4.5.0")
    ap.add_argument("--notes", default="", help="更新说明")
    ap.add_argument("--min-version", default="", help="强制更新的最低版本（可空）")
    ap.add_argument("--force", action="store_true", help="强制所有旧版更新")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""),
                    help="GitHub PAT（需 repo 权限）；也可设环境变量 GITHUB_TOKEN")
    ap.add_argument("--repo", default="knightlsy/printer-scan-tool", help="GitHub owner/repo")
    ap.add_argument("--no-git", action="store_true", help="跳过 git 推送到 master")
    ap.add_argument("--no-asset", action="store_true", help="不上传 exe 附件")
    args = ap.parse_args()

    TOKEN = args.token
    if not TOKEN:
        print("错误：缺少 GitHub token（用 --token 传入或设置环境变量 GITHUB_TOKEN）")
        sys.exit(1)
    if "/" not in args.repo:
        print("错误：--repo 需为 owner/repo 形式")
        sys.exit(1)
    OWNER, REPO = args.repo.split("/", 1)
    API = f"https://api.github.com/repos/{OWNER}/{REPO}"
    UPLOAD = f"https://uploads.github.com/repos/{OWNER}/{REPO}"

    if not os.path.isfile(args.exe):
        print(f"错误：找不到 exe：{args.exe}")
        sys.exit(1)

    version = args.version
    exe_name = os.path.basename(args.exe)
    root_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    print(f"[1/5] 仓库检查 / 新建（{OWNER}/{REPO}）")
    create_repo_if_needed(TOKEN, OWNER, REPO, "SCAN.GATE 打印机扫描共享工具")

    # 先写一份 version.json（拼接兜底直链），随源码先推到 master，
    # 让空仓库建立首次提交（GitHub 要求有提交才能建发行版）。
    print(f"[2/5] 写入 version.json 并推送源码（建立 master 首次提交）")
    manifest = build_manifest(args.exe, version, args.notes, args.min_version,
                              args.force, OWNER, REPO, download_url=None)
    with open(root_json, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"      version.json 已写入 {root_json}")
    if not args.no_git:
        push_master(version, TOKEN, args.repo)
    else:
        print(f"      [跳过 git 推送（--no-git）]")

    print(f"[3/5] 建/更新发行版 v{version}")
    rel = ensure_release(version, version, args.notes, TOKEN, API)
    rid = rel.get("id")
    print(f"      发行版 id={rid}")

    dl_url = None
    if not args.no_asset and rid:
        print(f"[4/5] 上传 exe 附件（GitHub 真实下载直链）")
        dl_url = upload_asset(rid, args.exe, exe_name, TOKEN, UPLOAD)
    else:
        print(f"[4/5] 跳过附件上传")

    if dl_url:
        print(f"[5/5] 用真实直链回写 version.json 并再次推送")
        manifest = build_manifest(args.exe, version, args.notes, args.min_version,
                                  args.force, OWNER, REPO, download_url=dl_url)
        with open(root_json, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False, indent=2))
        if not args.no_git:
            push_master(version, TOKEN, args.repo)
    else:
        print(f"[5/5] 未获真实直链，保留拼接兜底 URL（仍可下载）")

    if not args.no_git:
        set_default_branch(TOKEN, API, "master")

    print("\n=== 完成 ===")
    print(f"版本：v{version}")
    print(f"清单源：https://raw.githubusercontent.com/{OWNER}/{REPO}/master/version.json")
    print(f"下载直链：{manifest['files'][0]['url']}")


if __name__ == "__main__":
    main()
