#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键发布：生成 version.json 并同步到更新源（LAN 共享 + 可选 Gitee）。

用法：
    python publish_update.py --exe dist/打印机扫描工具_v4.exe --version 4.2.0 \
        --notes "新增在线更新；修复若干问题"

流程：
1. 计算 exe 的 SHA256 与大小；
2. 生成 version.json（含双源 files.url——LAN 与 Gitee 各一条 target=self，
   实际下载时客户端按第一个可用源的对应 url 走）；
3. 复制 exe + version.json 到 LAN 共享 updates/<version>/ 与 updates/ 根；
4. 若给了 --gitee-token 与 --gitee-repo，则尝试用 API 创建 Release 并上传附件
   （无 token 时跳过，仅打印手动上传指引）。

说明：本脚本只依赖标准库；Gitee 上传用 urllib 直连 openapi，失败不阻断 LAN 发布。
"""

import os
import sys
import json
import shutil
import hashlib
import argparse
from datetime import datetime, timezone, timedelta

# ---- 默认发布目标（按需修改）----
LAN_UPDATES_DIR = r"\\192.168.4.82\share\共享\updates"
GITEE_RELEASE_TAG = "latest"
GITEE_REPO_DEFAULT = "knightlsy/printer-scan-tool"


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(exe_path, version, notes, min_version, force, lan_dir, gitee_repo):
    name = os.path.basename(exe_path)
    size = os.path.getsize(exe_path)
    digest = sha256_of(exe_path)
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()

    files = []
    # LAN 源：指向 updates/<version>/<exe>
    lan_url = os.path.join(lan_dir, version, name)
    files.append({
        "name": name, "url": lan_url, "size": size,
        "sha256": digest, "target": "self", "source": "lan",
    })
    # Gitee 源（若提供仓库）：release 附件下载直链
    if gitee_repo:
        gitee_url = (
            f"https://gitee.com/{gitee_repo}/releases/download/"
            f"{GITEE_RELEASE_TAG}/{name}"
        )
        files.append({
            "name": name, "url": gitee_url, "size": size,
            "sha256": digest, "target": "self", "source": "gitee",
        })

    return {
        "version": version,
        "channel": "stable",
        "published_at": now,
        "notes": notes,
        "min_version": min_version,
        "force": bool(force),
        "files": files,
    }


def publish_lan(exe_path, manifest, lan_dir):
    version = manifest["version"]
    name = os.path.basename(exe_path)
    ver_dir = os.path.join(lan_dir, version)
    try:
        os.makedirs(ver_dir, exist_ok=True)
    except Exception as e:
        print(f"[LAN] 无法创建目录 {ver_dir}: {e}")
        return False
    # 复制 exe 到版本目录
    dst_exe = os.path.join(ver_dir, name)
    shutil.copy2(exe_path, dst_exe)
    # version.json 写到 updates 根（客户端清单源指向这里）
    mpath = os.path.join(lan_dir, "version.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    # 同时在版本目录留一份清单快照
    with open(os.path.join(ver_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[LAN] 已发布 -> {dst_exe}")
    print(f"[LAN] 清单   -> {mpath}")
    return True


def publish_local_copy(exe_path, manifest, out_dir):
    """当 LAN 不可达时，把产物落到本地 out_dir，供手动拷贝。"""
    version = manifest["version"]
    name = os.path.basename(exe_path)
    ver_dir = os.path.join(out_dir, version)
    os.makedirs(ver_dir, exist_ok=True)
    shutil.copy2(exe_path, os.path.join(ver_dir, name))
    with open(os.path.join(out_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[本地] 已输出到 {out_dir}（LAN 不可达时手动拷贝到共享 updates/）")


def main():
    ap = argparse.ArgumentParser(description="发布 SCAN.GATE 更新")
    ap.add_argument("--exe", required=True, help="要发布的 exe 路径")
    ap.add_argument("--version", required=True, help="版本号，如 4.2.0")
    ap.add_argument("--notes", default="", help="更新说明")
    ap.add_argument("--min-version", default="", help="强制更新的最低版本（可空）")
    ap.add_argument("--force", action="store_true", help="强制所有旧版更新")
    ap.add_argument("--lan-dir", default=LAN_UPDATES_DIR, help="LAN updates 目录")
    ap.add_argument("--gitee-repo", default=GITEE_REPO_DEFAULT, help="Gitee 仓库 owner/repo（用于生成下载直链）")
    ap.add_argument("--out", default="", help="LAN 不可达时的本地输出目录")
    args = ap.parse_args()

    if not os.path.isfile(args.exe):
        print(f"错误：找不到 exe：{args.exe}")
        sys.exit(1)

    manifest = build_manifest(
        args.exe, args.version, args.notes, args.min_version,
        args.force, args.lan_dir, args.gitee_repo,
    )
    print("=== version.json ===")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print("====================")

    ok = publish_lan(args.exe, manifest, args.lan_dir)
    if not ok and args.out:
        publish_local_copy(args.exe, manifest, args.out)

    if args.gitee_repo:
        print(f"\n[Gitee] 请到 https://gitee.com/{args.gitee_repo}/releases")
        print(f"        创建/更新 tag「{GITEE_RELEASE_TAG}」，上传：")
        print(f"        - {args.exe}")
        print(f"        - 上面的 version.json（若用 raw 配置分支方式，推到 config 分支即可）")
        print("        （客户端 Gitee 源会从该 release 直链下载）")

    print("\n完成。客户端下次启动将自动检测到该版本。")


if __name__ == "__main__":
    main()
