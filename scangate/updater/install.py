"""安装替换：解决 PyInstaller onefile exe 无法原地覆盖自身的问题。

思路（Windows）：
1. 备份当前 exe 为 <exe>.bak；
2. 写一个 update.bat 助手，它会：
   - 等待主进程（本 PID）退出；
   - move /y 新 exe → 当前 exe；
   - 启动新 exe，并轮询等待新进程写出「成功标记」；
   - 若超时未见成功标记 → 还原 .bak 并重启旧版（自动回滚）；
3. 主程序主动退出，把「替换 + 重启 + 回滚兜底」交给 bat 完成。

跨平台：仅本文件的脚本按 OS 分派。当前实现 Windows 分支；
macOS/Linux 预留 _write_helper_posix，可后续补全。
"""

import os
import sys
import time
import subprocess

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
    """当前运行的 exe 路径（frozen 态为 exe 本身；开发态为 python 解释器，仅供调试）。"""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
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


def install_and_relaunch(new_exe_path: str, new_version: str = "", wait_ok: int = 20) -> bool:
    """用新 exe 替换当前 exe 并重启；失败自动回滚。

    调用后应立即让主程序退出（return True 时由调用方执行 sys.exit）。
    返回 False 表示前置条件不满足（如非打包态），未做任何替换。
    """
    if not is_frozen():
        # 开发态无法自替换，直接返回 False，由上层提示「请手动替换」
        return False
    if not new_exe_path or not os.path.isfile(new_exe_path):
        return False

    target = current_exe()
    backup = target + ".bak"
    _ensure_dir()
    clear_ok_flag()
    write_pending(new_version, backup)

    if sys.platform.startswith("win"):
        _write_and_run_helper_win(new_exe_path, target, backup, wait_ok)
    else:
        _write_and_run_helper_posix(new_exe_path, target, backup, wait_ok)
    return True


def _write_and_run_helper_win(new_exe: str, target: str, backup: str, wait_ok: int) -> None:
    """生成并启动 Windows 批处理助手（分离进程，主程序退出后接力）。"""
    pid = os.getpid()
    bat_path = os.path.join(FLAG_DIR, "update.bat")
    ok_flag = OK_FLAG
    # 轮询次数：每次 sleep ~1s
    polls = max(5, int(wait_ok))
    name = os.path.basename(target)
    content = f"""@echo off
chcp 65001 >nul
setlocal enableextensions

set "TARGET={target}"
set "NEWEXE={new_exe}"
set "BACKUP={backup}"
set "OKFLAG={ok_flag}"

echo [SCAN.GATE Updater] 等待主程序退出...
:waitpid
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  ping 127.0.0.1 -n 2 >nul
  goto waitpid
)

echo [SCAN.GATE Updater] 备份并替换...
copy /y "%TARGET%" "%BACKUP%" >nul 2>&1
move /y "%NEWEXE%" "%TARGET%" >nul 2>&1
if errorlevel 1 (
  echo 替换失败，尝试回滚...
  goto rollback
)

echo [SCAN.GATE Updater] 启动新版本...
start "" "%TARGET%"

set /a c=0
:waitok
ping 127.0.0.1 -n 2 >nul
if exist "%OKFLAG%" goto success
set /a c+=1
if %c% lss {polls} goto waitok

echo [SCAN.GATE Updater] 新版本启动超时，回滚到旧版本...
:rollback
taskkill /IM "{name}" /F >nul 2>&1
if exist "%BACKUP%" (
  move /y "%BACKUP%" "%TARGET%" >nul 2>&1
  start "" "%TARGET%"
)
goto end

:success
echo [SCAN.GATE Updater] 更新成功。
del "%BACKUP%" >nul 2>&1

:end
del "%~f0" >nul 2>&1
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        return
    # 分离启动：CREATE_NEW_CONSOLE + DETACHED，主进程退出不影响 bat
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
    except Exception:
        pass


def _write_and_run_helper_posix(new_exe: str, target: str, backup: str, wait_ok: int) -> None:
    """macOS/Linux 助手（预留；逻辑与 Windows 对应）。"""
    pid = os.getpid()
    sh_path = os.path.join(FLAG_DIR, "update.sh")
    content = f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 1; done
cp -f "{target}" "{backup}"
mv -f "{new_exe}" "{target}"
chmod +x "{target}"
"{target}" &
c=0
while [ $c -lt {max(5, int(wait_ok))} ]; do
  [ -f "{OK_FLAG}" ] && break
  sleep 1; c=$((c+1))
done
if [ ! -f "{OK_FLAG}" ]; then
  pkill -f "{os.path.basename(target)}" 2>/dev/null
  mv -f "{backup}" "{target}"
  "{target}" &
else
  rm -f "{backup}"
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
