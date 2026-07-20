"""安装模式：把 onedir 文件夹安装到本机并创建桌面 / 开始菜单快捷方式。

设计要点：
- 安装位置：%LOCALAPPDATA%\\Programs\\PrinterScanTool\\（非管理员，普通用户可写）
- onedir 打包：主程序 exe 与 python313.dll 等依赖同目录，启动直接读本地文件，
  不再往 %TEMP% 解压，彻底规避 Windows Defender 对「自解压 exe 加载临时 DLL」
  的拦截（Failed to load Python DLL: python313.dll）。
- 快捷方式用 PowerShell 的 WScript.Shell COM 创建（沙箱无 pywin32，COM 原生可用）。
- 首次运行（来自便携位置 / 压缩包解压目录）自动安装到本机并重启，保证只有一个
  「已安装」副本在运行、被自动更新替换的是安装目录。

对外主要接口：
- is_installed()                     是否已安装到本机
- running_from_install_dir()         当前进程是否来自安装目录
- get_installed_exe()                安装目录内的主程序路径
- install_to_programs()              执行安装（复制文件夹 + 建快捷方式 + 写标记）
- maybe_install_and_relaunch()       首次运行钩子：未安装则安装并重启，返回 True 表示已重启
"""

import os
import sys
import shutil
import subprocess
import tempfile

from scangate.config import (
    INSTALL_DIR,
    APP_EXE_BASENAME,
    INSTALL_MARKER,
    START_MENU_GROUP,
    SHORTCUT_NAME,
)


def get_installed_exe() -> str:
    """安装目录内的主程序 exe 完整路径。"""
    return os.path.join(INSTALL_DIR, APP_EXE_BASENAME)


def running_from_install_dir() -> bool:
    """当前进程是否运行在安装目录内（据此判断是否已「安装态」）。"""
    if not getattr(sys, "frozen", False):
        return False
    exe = os.path.abspath(sys.executable)
    try:
        return os.path.commonpath([exe, os.path.abspath(INSTALL_DIR)]) == os.path.abspath(INSTALL_DIR)
    except Exception:
        return False


def is_installed() -> bool:
    """是否已安装到本机：标记文件存在且主程序存在。"""
    return os.path.isfile(INSTALL_MARKER) and os.path.isfile(get_installed_exe())


def _current_folder() -> str:
    """当前 exe 所在文件夹（onedir 模式即程序根目录）。"""
    return os.path.dirname(os.path.abspath(sys.executable))


def _robocopy_tree(src: str, dst: str) -> None:
    """复制整棵目录树；优先用系统 robocopy（可重试、跳过锁文件），失败回退 shutil。"""
    os.makedirs(dst, exist_ok=True)
    # 尝试 robocopy（Windows 自带，/E 含子目录 /R:2 重试2次 /W:1 间隔1s /NFL /NDL 静默）
    ps = shutil.which("robocopy") or shutil.which("ROBOCOPY.EXE")
    if ps:
        try:
            proc = subprocess.run(
                [ps, src, dst, "/E", "/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            # robocopy 退出码 <8 视为成功
            if proc.returncode < 8:
                return
        except Exception:
            pass
    # 回退：shutil 整树复制（先清后拷，避免旧文件残留）
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)


def _shortcut_ps1(target: str, link: str, workdir: str) -> str:
    """生成创建单个快捷方式的 PowerShell 脚本内容（UTF-8 BOM 写入后执行）。"""
    return (
        "$Wsh = New-Object -ComObject WScript.Shell\n"
        "$sc = $Wsh.CreateShortcut('%s')\n"
        "$sc.TargetPath = '%s'\n"
        "$sc.WorkingDirectory = '%s'\n"
        "$sc.IconLocation = '%s,0'\n"
        "$sc.Description = 'SCAN.GATE 打印机扫描共享工具'\n"
        "$sc.Save()\n"
    ) % (link, target, workdir, target)


def _create_shortcuts(target_exe: str, work_dir: str) -> None:
    """创建桌面 + 开始菜单快捷方式（PowerShell COM）。失败时静默忽略单个。"""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    start_menu = os.path.join(
        os.path.expanduser("~"),
        "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs",
        START_MENU_GROUP,
    )
    targets = []
    if os.path.isdir(desktop):
        targets.append(os.path.join(desktop, SHORTCUT_NAME))
    if os.path.isdir(os.path.dirname(start_menu)):
        os.makedirs(start_menu, exist_ok=True)
        targets.append(os.path.join(start_menu, SHORTCUT_NAME))

    for link in targets:
        try:
            ps = _shortcut_ps1(target_exe, link, work_dir)
            fd, tmp = tempfile.mkstemp(suffix=".ps1", prefix="sg_lnk_")
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                f.write(ps)
            subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", tmp],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            os.remove(tmp)
        except Exception:
            pass


def install_to_programs() -> str | None:
    """执行安装：把当前 onedir 文件夹复制到 INSTALL_DIR，建快捷方式，写标记。

    返回安装后的主程序路径；失败返回 None。
    """
    if not getattr(sys, "frozen", False):
        # 开发态无法安装（没有打包好的文件夹）
        return None
    src = _current_folder()
    exe_name = os.path.basename(os.path.abspath(sys.executable))
    dst_exe = os.path.join(INSTALL_DIR, exe_name)

    try:
        # 若目标已存在且正被占用（上一次没退干净），先尝试移除
        if os.path.isdir(INSTALL_DIR):
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        os.makedirs(os.path.dirname(INSTALL_DIR), exist_ok=True)
        _robocopy_tree(src, INSTALL_DIR)
    except Exception:
        return None

    if not os.path.isfile(dst_exe):
        return None

    # 建快捷方式
    _create_shortcuts(dst_exe, INSTALL_DIR)

    # 写安装标记（含版本/时间，便于排查）
    try:
        from scangate.config import VERSION
        with open(INSTALL_MARKER, "w", encoding="utf-8") as f:
            f.write(f"version={VERSION}\ninstalled_at={os.path.getmtime(dst_exe)}\n")
    except Exception:
        pass

    return dst_exe


def maybe_install_and_relaunch() -> bool:
    """首次运行钩子：未安装且非便携模式时，安装到本机并重启，返回 True 表示已重启。

    调用方约定：返回 True 后应直接退出当前进程（让安装目录的副本接管）。
    """
    # 开发态 / 显式便携模式：跳过
    if not getattr(sys, "frozen", False):
        return False
    if os.environ.get("SCANGATE_PORTABLE") == "1":
        return False
    # 已运行在安装目录：正常启动
    if running_from_install_dir():
        return False
    # 已安装但当前是从别处启动（如又解压了一份）：直接重启到安装目录副本
    if is_installed():
        inst = get_installed_exe()
        try:
            subprocess.Popen([inst], close_fds=True)
        except Exception:
            return False
        return True
    # 未安装：执行安装并重启
    inst = install_to_programs()
    if not inst:
        return False
    try:
        subprocess.Popen([inst], close_fds=True)
    except Exception:
        return False
    return True
