"""安装替换：解决 onedir 文件夹无法原地覆盖自身的问题。

思路（Windows）：
1. 下载物为 zip（新格式）或单 exe（旧格式兜底）；
2. 备份当前安装目录为 <dir>.bak；
3. 写一个 update.bat 助手，它会：
   - 等待主进程（本 PID）退出；
   - 把新文件夹 move 到安装目录（旧目录先移入 .bak）；
   - 启动新 exe，并轮询等待新进程写出「成功标记」；
   - 若超时未见成功标记 → 还原 .bak 并重启旧版（自动回滚）；
4. 主程序主动退出，把「替换 + 重启 + 回滚兜底」交给 bat 完成。

onedir 模式：主程序与 python313.dll 等同目录，启动直接读本地文件，不再临时解压，
彻底规避 Windows Defender 对「自解压 exe 加载临时 DLL」的拦截。
"""

import os
import sys
import time
import shutil
import zipfile
import subprocess
import tempfile

from scangate.config import INSTALL_DIR, APP_EXE_BASENAME
from scangate.installer import is_installed

# 新进程成功进入主循环后写出的标记文件（rollback.mark_started 负责写）
FLAG_DIR = os.path.join(os.path.expanduser("~"), ".printer_scan_update_state")
OK_FLAG = os.path.join(FLAG_DIR, "update_ok.flag")
PENDING_FLAG = os.path.join(FLAG_DIR, "pending.json")


def _ensure_dir() -> None:
    try:
        os.makedirs(FLAG_DIR, exist_ok=True)
    except Exception:
        pass


def current_exe() -> str:
    """当前运行的 exe 路径（frozen 态为 exe 本身）。"""
    return os.path.abspath(sys.executable)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def write_pending(new_version: str, backup_path: str) -> None:
    """记录「更新进行中」状态，供下次启动自检判断成功/回滚。"""
    import json
    _ensure_dir()
    try:
        with open(PENDING_FLAG, "w", encoding="utf-8") as f:
            json.dump(
                {"new_version": new_version, "backup": backup_path, "ts": time.time()},
                f, ensure_ascii=False,
            )
    except Exception:
        pass


def clear_ok_flag() -> None:
    try:
        if os.path.exists(OK_FLAG):
            os.remove(OK_FLAG)
    except Exception:
        pass


def _resolve_folder(artifact: str) -> str | None:
    """把下载物解析为「onedir 文件夹」。

    - .zip → 解压到临时目录，返回解压后的根文件夹
    - 单 .exe（旧格式兜底）→ 返回其所在目录（整目录替换）
    - 已经是目录 → 直接返回
    """
    if os.path.isdir(artifact):
        return artifact
    lower = artifact.lower()
    if lower.endswith(".zip"):
        try:
            tmp = tempfile.mkdtemp(prefix="sg_unzip_")
            with zipfile.ZipFile(artifact, "r") as z:
                z.extractall(tmp)
            # 若 zip 内有一层同名根目录，则下钻一层
            entries = [e for e in os.listdir(tmp) if not e.startswith("__MACOSX")]
            if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
                return os.path.join(tmp, entries[0])
            return tmp
        except Exception:
            return None
    # 单 exe 旧格式：用其所在目录作为替换单元
    return os.path.dirname(os.path.abspath(artifact))


def install_and_relaunch(new_artifact: str, new_version: str = "", wait_ok: int = 30) -> bool:
    """用新下载物替换当前安装并重启；失败自动回滚。

    调用后应立即让主程序退出（return True 时由调用方执行 sys.exit）。
    返回 False 表示前置条件不满足（如非打包态 / 下载物无效），未做任何替换。
    """
    if not is_frozen():
        return False
    if not new_artifact or not os.path.exists(new_artifact):
        return False

    src_folder = _resolve_folder(new_artifact)
    if not src_folder or not os.path.isdir(src_folder):
        return False

    # 目标安装目录：已安装到本机则替换安装目录，否则就地替换当前目录
    if is_installed():
        target_dir = INSTALL_DIR
    else:
        target_dir = os.path.dirname(os.path.abspath(sys.executable))

    new_exe = os.path.join(target_dir, APP_EXE_BASENAME)
    backup = target_dir + ".bak"
    _ensure_dir()
    clear_ok_flag()
    write_pending(new_version, backup)

    if sys.platform.startswith("win"):
        _write_and_run_helper_win(src_folder, target_dir, new_exe, backup, wait_ok)
    else:
        _write_and_run_helper_posix(src_folder, target_dir, new_exe, backup, wait_ok)
    return True


def _write_and_run_helper_win(src_folder: str, target_dir: str, new_exe: str,
                              backup: str, wait_ok: int) -> None:
    """生成并启动 Windows 批处理助手（分离进程，主程序退出后接力）。"""
    pid = os.getpid()
    bat_path = os.path.join(FLAG_DIR, "update.bat")
    ok_flag = OK_FLAG
    polls = max(5, int(wait_ok))
    exe_name = os.path.basename(new_exe)
    s = src_folder.replace("/", "\\")
    t = target_dir.replace("/", "\\")
    b = backup.replace("/", "\\")
    ne = new_exe.replace("/", "\\")
    content = f"""@echo off
chcp 65001 >nul
setlocal enableextensions

set "SRC={s}"
set "TARGET={t}"
set "NEWEXE={ne}"
set "BACKUP={b}"
set "OKFLAG={ok_flag}"
set "EXENAME={exe_name}"

echo [SCAN.GATE Updater] 等待主程序退出...
:waitpid
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  ping 127.0.0.1 -n 2 >nul
  goto waitpid
)

echo [SCAN.GATE Updater] 备份并替换...
if exist "%BACKUP%" rmdir /s /q "%BACKUP%" >nul 2>&1
if exist "%TARGET%" (
  move /y "%TARGET%" "%BACKUP%" >nul 2>&1
)
move /y "%SRC%" "%TARGET%" >nul 2>&1
if errorlevel 1 (
  echo 替换失败，尝试回滚...
  goto rollback
)

echo [SCAN.GATE Updater] 启动新版本...
start "" "%NEWEXE%"

set /a c=0
:waitok
ping 127.0.0.1 -n 2 >nul
if exist "%OKFLAG%" goto success
set /a c+=1
if %c% lss {polls} goto waitok

echo [SCAN.GATE Updater] 新版本启动超时，回滚到旧版本...
:rollback
taskkill /IM "%EXENAME%" /F >nul 2>&1
if exist "%BACKUP%" (
  if exist "%TARGET%" rmdir /s /q "%TARGET%" >nul 2>&1
  move /y "%BACKUP%" "%TARGET%" >nul 2>&1
  start "" "%NEWEXE%"
)
goto end

:success
echo [SCAN.GATE Updater] 更新成功。
if exist "%BACKUP%" rmdir /s /q "%BACKUP%" >nul 2>&1

:end
del "%~f0" >nul 2>&1
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        return
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
    except Exception:
        pass


def _write_and_run_helper_posix(src_folder: str, target_dir: str, new_exe: str,
                                backup: str, wait_ok: int) -> None:
    """macOS/Linux 助手（预留；逻辑与 Windows 对应）。"""
    pid = os.getpid()
    sh_path = os.path.join(FLAG_DIR, "update.sh")
    content = f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 1; done
[ -e "{backup}" ] && rm -rf "{backup}"
[ -e "{target_dir}" ] && mv -f "{target_dir}" "{backup}"
mv -f "{src_folder}" "{target_dir}"
"{new_exe}" &
c=0
while [ $c -lt {max(5, int(wait_ok))} ]; do
  [ -f "{OK_FLAG}" ] && break
  sleep 1; c=$((c+1))
done
if [ ! -f "{OK_FLAG}" ]; then
  pkill -f "{os.path.basename(new_exe)}" 2>/dev/null
  rm -rf "{target_dir}"
  mv -f "{backup}" "{target_dir}"
  "{new_exe}" &
else
  rm -rf "{backup}"
fi
rm -f "$0"
"""
    try:
        with open(sh_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(sh_path, 0o755)
        subprocess.Popen(["/bin/sh", sh_path], close_fds=True)
    except Exception:
        pass
