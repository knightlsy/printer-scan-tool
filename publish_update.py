#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键发布：生成 version.json 并同步到 Gitee 更新源。

用法：
    python publish_update.py --exe dist/打印机扫描工具_v4.exe --version 4.2.0 \
        --notes "新增在线更新；修复若干问题"

流程：
1. 计算 exe 的 SHA256 与大小；
2. 生成 version.json（含 Gitee release 下载直链）；
3. 打印手动上传指引（推 version.json 到 config 分支、传 exe 到 latest release）。

说明：本脚本只依赖标准库。如需全自动上传 Gitee，需提供 --gitee-token。
"""

import os
import sys
import json
import hashlib
import argparse
from datetime import datetime, timezone, timedelta

# ---- 默认发布目标 ----
GITEE_RELEASE_TAG = "latest"
GITEE_REPO_DEFAULT = "knightlsy/printer-scan-tool"


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(exe_path, version, notes, min_version, force, gitee_repo):
    name = os.path.basename(exe_path)
    size = os.path.getsize(exe_path)
    digest = sha256_of(exe_path)
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()

    files = []
    # 仅 Gitee 源：release 附件下载直链
    if gitee_repo:
        gitee_url = (
            f"https://gitee.com/{gitee_repo}/releases/download/"
            f"{GITEE_RELEASE_TAG}/{name}"
        )
        files.append({
            "name": name,
            "url": gitee_url,
            "size": size,
            "sha256": digest,
            "target": "self",
        })

    if not files:
        print("错误：未指定 Gitee 仓库，无法构建清单")
        sys.exit(1)

    return {
        "version": version,
        "channel": "stable",
        "published_at": now,
        "notes": notes,
        "min_version": min_version or "",
        "force": bool(force),
        "files": files,
    }


def main():
    ap = argparse.ArgumentParser(description="发布 SCAN.GATE 更新")
    ap.add_argument("--exe", required=True, help="要发布的 exe 路径")
    ap.add_argument("--version", required=True, help="版本号，如 4.2.0")
    ap.add_argument("--notes", default="", help="更新说明")
    ap.add_argument("--min-version", default="", help="强制更新的最低版本（可空）")
    ap.add_argument("--force", action="store_true", help="强制所有旧版更新")
    ap.add_argument("--gitee-repo", default=GITEE_REPO_DEFAULT,
                    help=f"Gitee 仓库 owner/repo（默认 {GITEE_REPO_DEFAULT}）")
    args = ap.parse_args()

    if not os.path.isfile(args.exe):
        print(f"错误：找不到 exe：{args.exe}")
        sys.exit(1)

    manifest = build_manifest(
        args.exe, args.version, args.notes, args.min_version,
        args.force, args.gitee_repo,
    )
    print("=== version.json ===")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print("====================")

    # 输出一份本地 version.json 供上传用
    out_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_publish_version.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n[输出] 清单已写入 {out_json}")

    print(f"\n[Gitee] 请到 https://gitee.com/{args.gitee_repo}/releases")
    print(f"        创建/更新 tag「{GITEE_RELEASE_TAG}」，上传：")
    print(f"        - {args.exe}（作为 Release 附件）")
    print(f"        - 将下面的 version.json 推送到 config 分支")
    print(f"\n[Gitee] config 分支推送方式：")
    print(f"        git checkout config")
    print(f"        cp _publish_version.json version.json")
    print(f"        git add version.json && git commit -m 'release v{args.version}' && git push origin config")
    print(f"        git checkout master")

    print("\n完成。客户端下次启动将自动检测到该版本。")


if __name__ == "__main__":
    main()
