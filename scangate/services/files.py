"""文件操作服务（后台执行）。

提供：列目录、上传、下载、删除。所有函数统一签名 (progress, cancel, ...)。
- 大文件读写分块进行，并周期性上报进度、检查取消令牌。
- 取消时在 finally 中清理已写入的半成品文件，避免残留。
"""

import os
import shutil
from typing import Callable


def list_files(progress: Callable, cancel, root: str) -> list[dict]:
    """列出目录内容，返回标准化条目列表（文件夹在前，再按名称排序）。"""
    progress(20, "读取文件列表…")
    items: list[dict] = []
    try:
        with os.scandir(root) as it:
            for entry in it:
                if cancel.is_cancelled():
                    raise InterruptedError()
                try:
                    st = entry.stat()
                    items.append(
                        {
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "size": st.st_size if entry.is_file() else 0,
                            "mtime": st.st_mtime,
                            "path": entry.path,
                        }
                    )
                except Exception:
                    pass
    except FileNotFoundError:
        raise
    except Exception as e:
        raise
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    progress(100, "完成")
    return items


def _safe_copy(src: str, dst: str, progress: Callable, cancel, label: str) -> str:
    total = max(1, os.path.getsize(src))
    copied = 0
    chunk = 1024 * 1024  # 1MB
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            if cancel.is_cancelled():
                fsrc.close()
                fdst.close()
                try:
                    os.remove(dst)
                except Exception:
                    pass
                raise InterruptedError()
            buf = fsrc.read(chunk)
            if not buf:
                break
            fdst.write(buf)
            copied += len(buf)
            progress(min(99.0, copied / total * 100.0), f"{label} {os.path.basename(src)}")
    progress(100, "完成")
    return dst


def upload(progress: Callable, cancel, local_path: str, dest_dir: str) -> str:
    """上传单个本地文件到共享目录。返回目标路径。"""
    name = os.path.basename(local_path)
    dest = os.path.join(dest_dir, name)
    return _safe_copy(local_path, dest, progress, cancel, "上传")


def download(progress: Callable, cancel, remote_path: str, local_path: str) -> str:
    """下载单个共享文件到本地。返回本地路径。"""
    return _safe_copy(remote_path, local_path, progress, cancel, "下载")


def delete(progress: Callable, cancel, path: str) -> bool:
    """删除文件或目录。"""
    if cancel.is_cancelled():
        raise InterruptedError()
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    progress(100, "已删除")
    return True
