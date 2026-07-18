#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键发布到 GitHub（CDN 加速版）：建仓库 + 源码/资源推 master + 打 tag + 建 release + 上传 exe 资产。

用法：
    python publish_update.py --exe dist/打印机扫描工具_v4.exe --version 4.6.0 \
        --notes "更新说明" --token ghp_xxx

做了什么：
1. 若仓库不存在则经 API 新建公开仓库（默认分支 master）；
2. 生成 version.json（结构化清单），写入仓库根目录，随源码推到 master；
   raw.githubusercontent.com/{owner}/{repo}/master/version.json 匿名可读、无 403，客户端清单源主用；
   cdn.jsdelivr.net/gh/{owner}/{repo}@master/version.json 作为清单源备线（version.json 体积小，jsDelivr 可正常服务）；
3. 打 git tag v{version} 并推送到 GitHub（tag 仅用于标记版本 / 发行版定位，不再把 42MB 的 exe 提交进仓库，
   以避免大文件 git 推送超时）；
4. 建 GitHub 发行版（tag=v{version}），并把 exe 作为发行版资产上传；
5. 生成 version.json，files[].urls 为「CDN 加速下载链」（exe 走发行版资产镜像）：
       [0] https://ghproxy.net/https://github.com/{owner}/{repo}/releases/download/v{ver}/printer-scan-tool.exe
           （ghproxy：国内对 GitHub Releases 资产的加速镜像，最快最稳，主用）
       [1] https://mirror.ghproxy.com/https://github.com/{owner}/{repo}/releases/download/v{ver}/printer-scan-tool.exe
           （ghproxy 备线）
       [2] https://github.com/{owner}/{repo}/releases/download/v{ver}/printer-scan-tool.exe
           （GitHub 官方直链，最后保底）
   说明：jsDelivr 的 /gh/ 仅能服务「仓库内的文件」，无法代理 Release 资产；而 42MB 的 exe 直接提交进
   仓库又会被当前发布环境的网络代理在推送时超时。因此 exe 统一走 Release 资产 + ghproxy 镜像加速，
   这同样是「CDN 加速」，且满足国内高速稳定下载。
6. 客户端 Updater 检测到新版本后，依次尝试 files[].urls（ghproxy → mirror → 官方直链），
   断点续传 + SHA256 校验 + 替换重启，实现「高速 + 稳定」的静默全自动更新。

token 仅经 --token / 环境变量 GITHUB_TOKEN 传入，绝不写入任何仓库文件。
"""

import os
import sys
import json
import shutil
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


def commit_and_push(version: str, token: str, repo: str, files: list) -> None:
    """把指定文件（通常是 version.json）提交并推到 master。

    注意：exe 不再提交进仓库（避免 42MB 大文件推送超时），exe 作为 Release 资产单独上传。
    """
    origin = f"https://x-access-token:{token}@github.com/{repo}.git"
    for fp in files:
        git("add", "-f", fp)
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


def push_tag(tag: str, token: str, repo: str) -> None:
    """打轻量 tag 并推送到 GitHub（发行版资产下载直链依赖 tag 定位版本）。"""
    origin = f"https://x-access-token:{token}@github.com/{repo}.git"
    git("tag", "-f", tag)
    try:
        git("push", origin, tag)
    except RuntimeError:
        git("push", "-f", origin, tag)


# ---------------- GitHub API ----------------
def gh_api(method, url, data=None, headers=None, raw=False, token=""):
    if isinstance(data, dict):
        payload = json.dumps(data).encode("utf-8")
        h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}",
             "User-Agent": "SCAN.GATE-Publisher"}
    else:
        payload = data
        # 自定义 headers 时不能丢掉鉴权与 User-Agent（否则上传附件会因无 token 被 400 拒绝）
        h = {"Authorization": f"Bearer {token}", "User-Agent": "SCAN.GATE-Publisher"}
        h.update(headers or {})
    req = urllib.request.Request(url, data=payload, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
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
                   urls=None, primary_url=None) -> dict:
    """构造结构化清单。

    name 取 exe 文件名（仓库内为 ASCII 的 printer-scan-tool.exe，URL 干净）；
    urls 为 CDN 加速候选链（ghproxy Release 资产镜像优先）；url 为主用（= urls[0]），
    供仍只认单 url 的旧客户端 / 界面展示使用。
    """
    name = os.path.basename(exe_path)
    size = os.path.getsize(exe_path)
    digest = sha256_of(exe_path)
    if not urls:
        # 兜底：仅 GitHub Releases 直链（无 CDN）
        primary = (f"https://github.com/{owner}/{repo}/releases/download/"
                   f"v{version}/{urllib.parse.quote(name)}")
        urls = [primary]
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
            "url": primary_url or urls[0],
            "urls": urls,
        }],
    }


def main():
    ap = argparse.ArgumentParser(
        description="发布 SCAN.GATE 更新到 GitHub（CDN 加速：ghproxy Release 资产镜像 + 官方直链多镜像）")
    ap.add_argument("--exe", required=True, help="要发布的 exe 路径")
    ap.add_argument("--version", required=True, help="版本号，如 4.6.0")
    ap.add_argument("--notes", default="", help="更新说明")
    ap.add_argument("--min-version", default="", help="强制更新的最低版本（可空）")
    ap.add_argument("--force", action="store_true", help="强制所有旧版更新")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""),
                    help="GitHub PAT（需 repo 权限）；也可设环境变量 GITHUB_TOKEN")
    ap.add_argument("--repo", default="knightlsy/printer-scan-tool", help="GitHub owner/repo")
    ap.add_argument("--no-git", action="store_true", help="跳过 git 推送到 master")
    ap.add_argument("--no-asset", action="store_true", help="不上传 exe 发行版资产（届时仅官方直链可用）")
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
    tag = f"v{version}"
    root = os.path.dirname(os.path.abspath(__file__))
    # 仓库内提交的 exe 用 ASCII 文件名（URL 干净）；安装时会改名为当前 exe
    REPO_EXE_NAME = "printer-scan-tool.exe"

    # CDN 加速下载地址（按优先级，exe 走 GitHub Releases 资产 + 镜像）：
    #   1) ghproxy 镜像 releases 资产（国内对 GitHub Releases 的加速，最快最稳，主用）
    #   2) mirror.ghproxy.com 镜像 releases 资产（ghproxy 备线）
    #   3) GitHub Releases 官方直链（最后保底）
    urls = [
        f"https://ghproxy.net/https://github.com/{OWNER}/{REPO}/releases/download/{tag}/{REPO_EXE_NAME}",
        f"https://mirror.ghproxy.com/https://github.com/{OWNER}/{REPO}/releases/download/{tag}/{REPO_EXE_NAME}",
        f"https://github.com/{OWNER}/{REPO}/releases/download/{tag}/{REPO_EXE_NAME}",
    ]
    primary = urls[0]

    print(f"[1/6] 仓库检查 / 新建（{OWNER}/{REPO}）")
    create_repo_if_needed(TOKEN, OWNER, REPO, "SCAN.GATE 打印机扫描共享工具")

    print(f"[2/6] 生成 version.json（CDN 加速多镜像清单）并准备提交")
    manifest = build_manifest(args.exe, version, args.notes, args.min_version,
                              args.force, OWNER, REPO, urls=urls, primary_url=primary)
    root_json = os.path.join(root, "version.json")
    with open(root_json, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"      version.json 已写入 {root_json}")
    # 顺手清理已废弃的 Gitee 分块目录（仅本地工作树，不影响功能）
    git("rm", "-r", "--ignore-unmatch", "update_chunks", check=False)

    if not args.no_git:
        # 只提交 version.json（源码改动需先自行 commit；exe 不进仓库，避免大文件推送超时）
        commit_and_push(version, TOKEN, args.repo, files=[root_json])
    else:
        print(f"      [跳过 git 推送（--no-git）]")

    print(f"[3/6] 打 git tag {tag} 并推送（发行版资产下载直链依赖此 tag 定位版本）")
    if not args.no_git:
        push_tag(tag, TOKEN, args.repo)
    else:
        print(f"      [跳过打 tag（--no-git）]")

    print(f"[4/6] 建/更新发行版 {tag}")
    rel_notes = (args.notes or "") + f"\n\nCDN 加速下载（推荐，国内更快更稳）：\n{primary}\n\n"
    rel_notes += "客户端将自动按 ghproxy → mirror.ghproxy → 官方直链 顺序尝试下载并静默安装。"
    rel = ensure_release(tag, version, rel_notes, TOKEN, API)
    rid = rel.get("id")
    print(f"      发行版 id={rid}")

    if not args.no_asset and rid:
        print(f"[5/6] 上传 exe 发行版资产（供镜像加速与人工下载页）")
        upload_asset(rid, args.exe, REPO_EXE_NAME, TOKEN, UPLOAD)
    else:
        print(f"[5/6] 跳过附件上传")

    if not args.no_git:
        set_default_branch(TOKEN, API, "master")

    print("\n=== 完成 ===")
    print(f"版本：v{version}  (tag={tag})")
    print(f"清单源（主）：https://raw.githubusercontent.com/{OWNER}/{REPO}/master/version.json")
    print(f"清单源（备/CDN）：https://cdn.jsdelivr.net/gh/{OWNER}/{REPO}@master/version.json")
    print(f"CDN 加速主下载链：{primary}")
    print(f"全部镜像：")
    for u in urls:
        print(f"  - {u}")


if __name__ == "__main__":
    main()
