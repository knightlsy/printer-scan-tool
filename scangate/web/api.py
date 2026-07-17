"""后端桥：暴露给前端 JS 的 Python API（pywebview js_api）。

设计要点：
- 所有阻塞操作（net use 连接、列目录、上传下载、PDF 预览）都在独立线程里跑，
  主线程（WebView2 渲染循环）永不阻塞，界面不会卡死。
- 进度 / 结果通过 webview.windows[0].evaluate_js(...) 推回前端全局回调，
  因此前端需要预先定义 onStatus / onProgress / onList / onPreview / onOverlay 等函数。
- 文件选择对话框用 webview.create_file_dialog，由 JS 触发 API 方法时在 API 线程内弹出。
- 取消：每个任务持有一个 threading.Event，前端调用 cancel() 即可中断。
"""

import os
import re
import io
import json
import base64
import getpass
import threading
from datetime import datetime

# 真实姓名校验（含《百家姓》姓氏合法性校验）统一在 scangate.services.surnames 中完成

import webview
from webview.window import FixPoint

from scangate.config import (
    ConfigManager, ConnectionConfig, ServerProfile,
    APP_NAME, VERSION, AUTHOR, COPYRIGHT,
    LINK_INTERNAL, LINK_EXTERNAL,
)
from scangate.services.connection import connect, disconnect
from scangate.services.files import list_files, upload, download, delete
from scangate.services.preview import make_preview
from scangate.services.compress import compress, human as _human_size
from scangate.services.auditlog import write_session_log
from scangate.updater import Updater
from scangate.updater.settings import load_settings as _load_update_settings, set_prefs as _set_update_prefs


class _Cancel:
    """把 threading.Event 适配成 services 需要的取消令牌。"""

    def __init__(self, ev: threading.Event):
        self._ev = ev

    def is_cancelled(self) -> bool:
        return self._ev.is_set()

    def cancel(self) -> None:
        self._ev.set()


def _img_to_dataurl(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class Api:
    def __init__(self):
        self.cm = ConfigManager()
        self.servers = self.cm.servers
        self.current_id = self.cm.current_id
        self.cfg = self._active_cfg()
        self.connected = False
        self.items: list = []
        self._active = None            # 当前任务 id
        self._cancel: threading.Event | None = None
        self._maximized = False        # 无边框窗口的最大化状态（用于切换）
        # 操作人：优先用配置里填写的姓名，否则回退到本机登录账号
        self.operator = self.cm.operator or self._windows_account()
        self._session = None           # 当前连接会话审计记录（连接时建立，断开/关闭时落盘）
        self._updater = None           # 最近一次 Updater 实例（缓存检测到的清单）

    # ---------------- 连接会话审计日志 ----------------
    @staticmethod
    def _windows_account() -> str:
        """返回本机 Windows 登录账号（形如 COMPUTER\\user），用于操作溯源。"""
        user = os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser()
        comp = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or ""
        if comp and user and not user.startswith(comp + "\\"):
            return f"{comp}\\{user}"
        return user

    def _session_op(self, op_type, description, target="", before_state="",
                    after_state="", success=True, reason="", detail="") -> None:
        """把一次文件操作记录进「当前连接会话」（仅会话内有效）。

        会话断开 / 关闭窗口时，这些记录会汇总成唯一一条日志写入共享 log 目录。
        """
        if not self._session:
            return
        self._session["ops"].append({
            "time": datetime.now(),
            "op_type": op_type,
            "description": description,
            "target": target,
            "before_state": before_state,
            "after_state": after_state,
            "success": success,
            "reason": reason,
            "detail": detail,
        })

    def _flush_session(self) -> None:
        """断开连接 / 关闭窗口时，把整个会话汇成一条日志写入共享 log 目录。

        写日志为尽力而为：任何异常都被吞掉，绝不影响主业务流程。
        """
        s = self._session
        if not s:
            return
        try:
            write_session_log(
                host=s["host"],
                share=s["share"],
                operator=s["operator"],
                account=s["account"],
                start_dt=s["start"],
                end_dt=datetime.now(),
                server_unc=s["server_unc"],
                subfolder=s["subfolder"],
                ops=s["ops"],
                app_version=f"{APP_NAME} v{VERSION}",
            )
        except Exception:
            pass
        finally:
            self._session = None
    def _active_profile(self) -> ServerProfile | None:
        for s in self.servers:
            if s.id == self.current_id:
                return s
        return self.servers[0] if self.servers else None

    def _active_cfg(self) -> ConnectionConfig:
        p = self._active_profile()
        if not p:
            p = ServerProfile()
            self.servers.append(p)
            self.current_id = p.id
        return ConnectionConfig(
            host=p.host, share=p.share, subfolder=p.subfolder,
            username=p.username, password=p.password,
        )

    def _persist(self) -> None:
        self.cm.servers = self.servers
        self.cm.current_id = self.current_id
        self.cm.save()

    # ---------------- 通信底层 ----------------
    def _emit(self, code: str) -> None:
        try:
            webview.windows[0].evaluate_js(code)
        except Exception:
            pass

    def _call(self, func: str, *args) -> None:
        """拼出 JS 调用：func(arg1, arg2, ...) 并把结果推回前端。"""
        parts = [json.dumps(a, ensure_ascii=False) for a in args]
        self._emit(f"{func}({','.join(parts)})")

    def _start(self, task_id: str, fn, overlay: bool = True, cancelable: bool = True) -> None:
        """启动一个后台任务。fn(progress, cancel)。"""
        if self._active:
            return
        self._active = task_id
        self._cancel = threading.Event()
        cancel = _Cancel(self._cancel)
        if overlay:
            self._call("onOverlay", True, cancelable)

        def run() -> None:
            try:
                fn(lambda p, m: self._call("onProgress", p, m), cancel)
            except Exception as e:  # 任务内未捕获的异常，统一上报
                self._call("onStatus", f"错误：{e}", "error")
            finally:
                self._active = None
                self._cancel = None
                if overlay:
                    self._call("onOverlay", False, False)

        threading.Thread(target=run, daemon=True).start()

    def cancel(self) -> None:
        """取消当前活动任务。"""
        if self._cancel:
            self._cancel.set()

    # ---------------- 初始化 ----------------
    def get_init(self) -> dict:
        return {
            "app_name": APP_NAME,
            "version": VERSION,
            "author": AUTHOR,
            "copyright": COPYRIGHT,
            "connected": self.connected,
            "current_id": self.current_id,
            "operator": self.cm.operator,
            "needs_name": not bool(self.cm.operator),
            "update": self._update_prefs_dict(),
            "servers": [
                {"id": s.id, "name": s.name, "host": s.host, "subfolder": s.subfolder}
                for s in self.servers
            ],
            "config": {
                "host": self.cfg.host,
                "share": self.cfg.share,
                "subfolder": self.cfg.subfolder,
                "username": self.cfg.username,
                "password": self.cfg.password,
            },
        }

    def about(self) -> dict:
        return {
            "app_name": APP_NAME,
            "version": VERSION,
            "author": AUTHOR,
            "copyright": COPYRIGHT,
            "link_internal": LINK_INTERNAL,
            "link_external": LINK_EXTERNAL,
        }

    # ---------------- 首次启动强制实名 ----------------
    def set_operator(self, name: str) -> dict:
        """首次启动强制登记操作人真实姓名，并持久化到本地配置。

        校验规则：去前导空格后，首 1~2 字须为《百家姓》收录或另有正式记录的
        中国姓氏（复姓匹配前两字、单姓匹配首字）；其余规则（非空、至少 2 字、
        仅含中文与间隔号）一并校验。校验通过才写入，否则返回错误信息。
        """
        from scangate.services.surnames import check_realname

        res = check_realname(name)
        if not res["ok"]:
            return res
        real = (name or "").strip()
        self.cm.operator = real
        self.operator = real
        try:
            self.cm.save()
        except Exception:
            return {"ok": False, "error": "姓名保存失败，请重试"}
        return {"ok": True, "operator": real}

    # ---------------- 在线更新 ----------------
    def _update_prefs_dict(self) -> dict:
        try:
            s = _load_update_settings()
            return {"auto_check": s.auto_check, "auto_install": s.auto_install}
        except Exception:
            return {"auto_check": True, "auto_install": False}

    def _on_update_event(self, event: str, payload: dict) -> None:
        """把 Updater 的统一事件映射为前端全局回调。"""
        if event == "checking":
            self._call("onUpdateStatus", "checking", "正在检查更新…")
        elif event == "up_to_date":
            self._call("onUpdateStatus", "up_to_date",
                       f"已是最新版本（v{payload.get('version','')}）")
        elif event == "found":
            self._call("onUpdateFound", payload)
        elif event == "error":
            self._call("onUpdateStatus", "error", payload.get("message", "更新出错"))
        elif event == "progress":
            self._call("onUpdateProgress", payload.get("stage", "downloading"),
                       payload.get("pct", 0), payload.get("speed", 0))
        elif event == "installing":
            self._call("onUpdateStatus", "installing", "正在安装，程序即将重启…")
        elif event == "ready":
            self._call("onUpdateStatus", "ready", "更新已就绪，正在重启应用…")
            # 安装脚本已接管，主程序主动退出把替换/重启交给它
            try:
                self._flush_session()
            except Exception:
                pass
            self._call("onUpdateStatus", "restarting", "正在重启…")
            import threading as _t
            _t.Timer(0.8, self._exit_for_update).start()
        elif event == "need_manual":
            self._call("onUpdateStatus", "need_manual",
                       f"新版本已下载到：{payload.get('path','')}，请手动替换后重启")

    def _exit_for_update(self) -> None:
        try:
            webview.windows[0].destroy()
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            pass

    def check_update(self, silent: bool = False) -> None:
        """手动/自动检查更新（后台线程，绝不阻塞界面）。"""
        def run():
            try:
                up = Updater(VERSION, on_event=self._on_update_event)
                up.check(silent=silent)
                self._updater = up
            except Exception as e:
                if not silent:
                    self._call("onUpdateStatus", "error", f"检查更新失败：{e}")
        threading.Thread(target=run, daemon=True).start()

    def download_and_install_update(self) -> None:
        """下载最近一次检测到的新版本并安装重启（后台线程）。"""
        def run():
            try:
                up = getattr(self, "_updater", None)
                if up is None or not getattr(up, "_latest", None):
                    up = Updater(VERSION, on_event=self._on_update_event)
                    if not up.check(silent=True):
                        self._call("onUpdateStatus", "error", "没有可用更新")
                        return
                up.download_and_install(cancel=lambda: self._cancel.is_set() if self._cancel else False)
            except Exception as e:
                self._call("onUpdateStatus", "error", f"更新失败：{e}")
        threading.Thread(target=run, daemon=True).start()

    def set_update_prefs(self, auto_check: bool = None, auto_install: bool = None) -> dict:
        """更新自动检查/自动安装偏好，持久化并返回最新值。"""
        try:
            s = _set_update_prefs(auto_check=auto_check, auto_install=auto_install)
            return {"ok": True, "auto_check": s.auto_check, "auto_install": s.auto_install}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def startup_update_check(self) -> None:
        """启动后由前端调用一次：写成功标记、报告上次更新结果、按偏好自动检查。"""
        # 1) 写「成功标记」，让 update.bat 判定新版启动成功、清理 .bak
        try:
            from scangate.updater import rollback as _rb
            _rb.mark_started()
            result, info = _rb.on_startup(VERSION)
            if result == "success":
                self._call("onUpdateStatus", "updated", f"已更新到 v{info}")
            elif result == "rolledback":
                self._call("onUpdateStatus", "rolledback",
                           "上次更新失败，已自动回滚到上一可用版本")
        except Exception:
            pass
        # 2) 按偏好后台自动检查（静默：无更新不打扰）
        try:
            s = _load_update_settings()
            if s.auto_check:
                self.check_update(silent=True)
        except Exception:
            pass

    # ---------------- 无边框窗口控制 ----------------
    def minimize(self) -> None:
        """最小化窗口。"""
        try:
            webview.windows[0].minimize()
        except Exception:
            pass

    def toggle_maximize(self) -> None:
        """在最大化 / 还原之间切换（无边框下需自行维护状态）。"""
        try:
            w = webview.windows[0]
            if self._maximized:
                w.restore()
            else:
                w.maximize()
            self._maximized = not self._maximized
        except Exception:
            pass

    def close_window(self) -> None:
        """关闭并销毁窗口。关闭前先把当前会话审计日志落盘。"""
        try:
            self._flush_session()
        except Exception:
            pass
        try:
            webview.windows[0].destroy()
        except Exception:
            pass

    def open_url(self, url: str) -> None:
        """在系统默认浏览器中打开外部链接（如飞书添加联系人）。

        webbrowser 延迟到首次调用时再导入：其模块加载会探测系统浏览器，
        属非必要启动开销，延迟可略微加快冷启动。
        """
        if not url:
            return
        try:
            import webbrowser
            webbrowser.open(url, new=2)
        except Exception:
            pass

    # ---------------- 窗口尺寸 / 八向自由缩放 ----------------
    # 各方向对应的「固定锚点」(FixPoint)：缩放时该锚点保持不动，仅另一侧随鼠标移动。
    #   n  : 底-左固定 (SOUTH|WEST)      s  : 顶-左固定 (NORTH|WEST)
    #   e  : 顶-左固定 (NORTH|WEST)      w  : 顶-右固定 (NORTH|EAST)
    #   ne : 底-左固定 (SOUTH|WEST)      nw : 底-右固定 (SOUTH|EAST)
    #   se : 顶-左固定 (NORTH|WEST)      sw : 顶-右固定 (NORTH|EAST)
    _DIR_FIX = {
        "n":  FixPoint.SOUTH | FixPoint.WEST,
        "s":  FixPoint.NORTH | FixPoint.WEST,
        "e":  FixPoint.NORTH | FixPoint.WEST,
        "w":  FixPoint.NORTH | FixPoint.EAST,
        "ne": FixPoint.SOUTH | FixPoint.WEST,
        "nw": FixPoint.SOUTH | FixPoint.EAST,
        "se": FixPoint.NORTH | FixPoint.WEST,
        "sw": FixPoint.NORTH | FixPoint.EAST,
    }

    def get_window_rect(self) -> dict | None:
        """返回当前窗口几何信息 {x, y, width, height}（供前端缩放时作为基准）。"""
        try:
            w = webview.windows[0]
            return {"x": w.x, "y": w.y, "width": w.width, "height": w.height}
        except Exception:
            return None

    def resize_window(self, width: int, height: int, direction: str) -> None:
        """按方向自由缩放窗口。direction ∈ {n,s,e,w,ne,nw,se,sw}。

        借助 pywebview 的 fix_point 锚点机制，仅需传入目标尺寸与方向，
        窗口位置（如从左边/上边缩放时的位移）由后端原生处理，避免 JS 管理坐标。
        """
        try:
            w = webview.windows[0]
            fix = self._DIR_FIX.get(direction, FixPoint.NORTH | FixPoint.WEST)
            w.resize(int(width), int(height), fix)
        except Exception:
            pass

    # ---------------- 配置（当前生效档） ----------------
    def save_config(self, cfg: dict) -> bool:
        try:
            p = self._active_profile()
            if p is None:
                p = ServerProfile()
                self.servers.append(p)
                self.current_id = p.id
            before = f"服务器：{p.unc_base}\\{p.subfolder}"
            p.host = cfg.get("host", p.host)
            p.share = cfg.get("share", p.share)
            p.subfolder = cfg.get("subfolder", p.subfolder)
            p.username = cfg.get("username", p.username)
            p.password = cfg.get("password", p.password)
            self.cfg = self._active_cfg()
            self._persist()
        except Exception:
            return False
        return True

    # ---------------- 多档服务器管理 ----------------
    def list_servers(self) -> list:
        """返回全部已保存的服务器配置（含完整字段，供编辑/删除）。"""
        return [
            {
                "id": s.id,
                "name": s.name,
                "host": s.host,
                "share": s.share,
                "subfolder": s.subfolder,
                "username": s.username,
                "password": s.password,
            }
            for s in self.servers
        ]

    def save_server(self, data: dict) -> str | None:
        """新增或更新一份服务器配置。返回该档 id；失败返回 None。"""
        try:
            sid = (data.get("id") or "").strip()
            prof = None
            if sid:
                for s in self.servers:
                    if s.id == sid:
                        prof = s
                        break
            if prof is None:
                prof = ServerProfile()
                self.servers.append(prof)
                is_new = True
            else:
                is_new = False
            prof.name = (data.get("name") or "").strip() or "未命名服务器"
            prof.host = data.get("host", prof.host)
            prof.share = data.get("share", prof.share)
            prof.subfolder = data.get("subfolder", prof.subfolder)
            prof.username = data.get("username", prof.username)
            prof.password = data.get("password", prof.password)
            # 第一档自动成为当前生效档
            if len(self.servers) == 1:
                self.current_id = prof.id
            self.cfg = self._active_cfg()
            self._persist()
            return prof.id
        except Exception:
            return None

    def delete_server(self, sid: str) -> bool:
        """删除指定服务器配置。不允许删空（至少保留一档）。返回是否真正删除。"""
        try:
            before = len(self.servers)
            self.servers = [s for s in self.servers if s.id != sid]
            if not self.servers:
                self.servers = [ServerProfile()]
            if self.current_id == sid or self.current_id not in {s.id for s in self.servers}:
                self.current_id = self.servers[0].id
            self.cfg = self._active_cfg()
            self._persist()
            return before != len(self.servers)
        except Exception:
            return False

    def use_server(self, sid: str) -> bool:
        """将某档设为当前生效配置（同步到主面板字段）。"""
        for s in self.servers:
            if s.id == sid:
                self.current_id = sid
                self.cfg = self._active_cfg()
                self._persist()
                return True
        return False

    # ---------------- 连接 ----------------
    def connect(self) -> None:
        if self._active:
            return
        self._call("onStatus", "连接中…", "warn")

        def fn(progress, cancel):
            try:
                connect(progress, cancel, self.cfg)
            except Exception as e:
                self._call("onStatus", f"连接失败：{e}", "error")
                return
            self.connected = True
            # 建立本次连接会话的审计记录（断开 / 关闭窗口时落盘为一条日志）
            self._session = {
                "start": datetime.now(),
                "operator": self.cm.operator,
                "account": self._windows_account(),
                "host": self.cfg.host,
                "share": self.cfg.share,
                "server_unc": self.cfg.unc_base,
                "subfolder": self.cfg.subfolder,
                "ops": [],
            }
            self._call("onStatus", "已连接", "success")
            self._call("onConfigStatus", "已连接", True)
            items = list_files(progress, cancel, self.cfg.root_path)
            self.items = items
            self._call("onList", items)
            self._call("onStatus", f"共 {len(items)} 项", "success")

        self._start("connect", fn)

    def disconnect(self) -> None:
        if self._active or not self.connected:
            return

        def fn(progress, cancel):
            # 先汇总落盘本次会话日志（此时共享会话仍在，能写进共享 log 目录）
            self._flush_session()
            disconnect(progress, cancel, self.cfg)
            self.connected = False
            self._call("onStatus", "已断开", "error")
            self._call("onConfigStatus", "未连接", False)

        self._start("disconnect", fn)

    # ---------------- 文件列表 ----------------
    def refresh(self) -> None:
        if not self.connected:
            self._call("onStatus", "请先连接共享", "error")
            return
        if self._active:
            return

        def fn(progress, cancel):
            items = list_files(progress, cancel, self.cfg.root_path)
            self.items = items
            self._call("onList", items)
            self._call("onStatus", f"共 {len(items)} 项", "success")

        self._start("list", fn)

    # ---------------- 上传 ----------------
    def upload(self) -> bool:
        if not self.connected:
            self._call("onStatus", "请先连接共享", "error")
            return False
        if self._active:
            return False
        try:
            paths = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=True
            )
        except Exception as e:
            self._call("onStatus", f"无法打开文件选择：{e}", "error")
            return False
        if not paths:
            return False
        dest = self.cfg.root_path
        results = {"ok": 0, "fail": 0}

        def fn(progress, cancel):
            names = [os.path.basename(p) for p in paths]
            for p in paths:
                if cancel.is_cancelled():
                    break
                try:
                    upload(progress, cancel, p, dest)
                    results["ok"] += 1
                except Exception:
                    results["fail"] += 1
            self._session_op(
                "上传文件",
                f"向共享目录 {dest} 上传了 {results['ok']} 个文件（失败 {results['fail']} 个）",
                target=dest,
                before_state=f"待上传本地文件 {len(paths)} 个：\n" + "\n".join(names),
                after_state=(
                    f"已上传成功 {results['ok']} 个到 {dest}；"
                    f"失败 {results['fail']} 个" if results["fail"]
                    else f"全部 {results['ok']} 个文件已成功上传到 {dest}"
                ),
                success=results["fail"] == 0,
                detail="本次上传文件清单：\n" + "\n".join(names),
            )
            self._call(
                "onStatus",
                f"上传完成：成功 {results['ok']} / 失败 {results['fail']}",
                "success",
            )
            try:
                items = list_files(progress, cancel, dest)
                self.items = items
                self._call("onList", items)
            except Exception:
                pass

        self._start("upload", fn)
        return True

    # ---------------- 下载 ----------------
    def download(self, path: str) -> bool:
        if not path:
            self._call("onStatus", "请先选择要下载的文件", "error")
            return False
        if not self.connected:
            self._call("onStatus", "请先连接共享", "error")
            return False
        if self._active:
            return False
        name = os.path.basename(path)
        try:
            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG, save_filename=name
            )
            # create_file_dialog 返回 tuple 或 None，需解包为路径字符串
            dest = result[0] if isinstance(result, (tuple, list)) and result else result
        except Exception as e:
            self._call("onStatus", f"无法打开保存对话框：{e}", "error")
            return False
        if not dest:
            return False

        def fn(progress, cancel):
            # 操作前：记录远程源文件信息（下载后源仍在，便于溯源）
            try:
                st = os.stat(path)
                before = (f"远程文件存在：{name}\n大小：{st.st_size} 字节\n"
                          f"修改时间：{__import__('datetime').datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception:
                before = f"远程文件：{path}（无法读取源状态）"
            try:
                download(progress, cancel, path, dest)
                # 下载成功后自动删除服务器上的源文件
                try:
                    delete(progress, cancel, path)
                    del_note = "；已自动删除服务器源文件"
                except Exception as de:
                    del_note = f"；但服务器源文件删除失败：{de}"
                self._session_op(
                    "下载文件",
                    f"将共享文件 {name} 下载到本机 {dest}",
                    target=path,
                    before_state=before,
                    after_state=f"已下载到本机：{dest}{del_note}",
                    success=True,
                )
                self._call("onStatus", "下载完成" + del_note, "success")
                # 刷新文件列表，移除已删除的服务器文件
                try:
                    items = list_files(progress, cancel, os.path.dirname(path))
                    self.items = items
                    self._call("onList", items)
                except Exception:
                    pass
            except Exception as e:
                self._session_op(
                    "下载文件",
                    f"下载共享文件 {name} 失败",
                    target=path,
                    before_state=before,
                    after_state="下载失败，本机未生成文件",
                    success=False, reason=str(e),
                )
                self._call("onStatus", f"下载失败：{e}", "error")

        self._start("download", fn)
        return True

    # ---------------- 小工具：PDF 压缩 ----------------
    def pick_pdf(self):
        """弹出系统文件选择框，选中本地 PDF 后返回其完整路径。

        在 API 线程内直接弹出对话框（与 upload 的 OPEN_DIALOG 同源机制）。
        返回 None 表示用户取消或未选文件。
        """
        try:
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("PDF 文件 (*.pdf)",),
            )
        except Exception as e:
            self._call("onStatus", f"无法打开文件选择：{e}", "error")
            return None
        if not result:
            return None
        # create_file_dialog 返回 tuple 或 None，需解包为路径字符串
        return result[0] if isinstance(result, (tuple, list)) and result else result

    def compress_pdf(self, path: str, level: str = "standard", rate: int = None) -> bool:
        """压缩本地 PDF，另存为「原名_compressed.pdf」（同名已存在则追加序号）。

        压缩级别 level：standard（无损压缩）/ high（重光栅化）/ custom（rate 自定义压缩率）。
        rate 仅 custom 生效，取值 0-100，越大压缩越狠（画质越低）。
        """
        if not path or not os.path.isfile(path):
            self._call("onStatus", "请先选择要压缩的 PDF 文件", "error")
            return False
        if not path.lower().endswith(".pdf"):
            self._call("onStatus", "仅支持 PDF 文件", "error")
            return False
        if self._active:
            return False
        base, _ = os.path.splitext(path)
        dst = f"{base}_compressed.pdf"
        i = 1
        while os.path.exists(dst):
            dst = f"{base}_compressed_{i}.pdf"
            i += 1

        def fn(progress, cancel):
            def _prog(pct, msg):
                progress(pct, msg)
                self._call("onToolProgress", pct)

            try:
                orig, new = compress(path, dst, level, rate, _prog)
                saved = (1 - new / orig) * 100 if orig else 0
                if new < orig:
                    msg = (
                        f"压缩完成：{_human_size(orig)} → {_human_size(new)}"
                        f"（节省 {saved:.0f}%，已保存：{dst}）"
                    )
                else:
                    msg = (
                        f"压缩后未减小：{_human_size(orig)} → {_human_size(new)}"
                        f"（该文件重光栅化后体积未变小，建议提高压缩率，已保存：{dst}）"
                    )
                self._call("onStatus", msg, "success")
                self._call("onToolStatus", msg, "success")
                self._call("onToolResult", orig, new, round(saved, 1), dst)
            except Exception as e:
                self._call("onStatus", f"压缩失败：{e}", "error")
                self._call("onToolStatus", f"压缩失败：{e}", "error")

        self._start("compress", fn)
        return True

    # ---------------- 删除 ----------------
    def delete(self, path: str) -> bool:
        if not path:
            self._call("onStatus", "请先选择要删除的文件", "error")
            return False
        if not self.connected:
            self._call("onStatus", "请先连接共享后再删除", "error")
            return False
        if self._active:
            return False
        name = os.path.basename(path)

        def fn(progress, cancel):
            # 操作前：记录被删文件信息，供审计对比
            try:
                st = os.stat(path)
                before = (f"文件存在：{name}\n大小：{st.st_size} 字节\n"
                          f"修改时间：{__import__('datetime').datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception:
                before = f"目标：{name}（删除前无法读取状态，可能已不存在）"
            try:
                delete(progress, cancel, path)
                self._session_op(
                    "删除文件",
                    f"在共享目录中删除了文件 {name}",
                    target=path,
                    before_state=before,
                    after_state=f"文件 {name} 已被删除，目录中不再存在",
                    success=True,
                )
                self._call("onStatus", "已删除", "success")
            except Exception as e:
                self._session_op(
                    "删除文件",
                    f"删除文件 {name} 失败",
                    target=path,
                    before_state=before,
                    after_state="删除失败，文件可能仍然存在",
                    success=False, reason=str(e),
                )
                self._call("onStatus", f"删除失败：{e}", "error")
                return
            try:
                items = list_files(progress, cancel, self.cfg.root_path)
                self.items = items
                self._call("onList", items)
            except Exception:
                pass

        self._start("delete", fn)
        return True

    # ---------------- 预览 ----------------
    def preview(self, path: str, page: int = 0) -> bool:
        if not path:
            self._call("onPreview", None)
            return False
        if self._active:
            return False

        def fn(progress, cancel):
            try:
                res = make_preview(progress, cancel, path, int(page))
                img = res.get("image")
                data = _img_to_dataurl(img) if img else None
                self._call(
                    "onPreview",
                    {
                        "data": data,
                        "name": os.path.basename(path),
                        "page": res.get("page", 0),
                        "total": res.get("total", 1),
                        "pdf": res.get("pdf", False),
                        "error": None,
                    },
                )
            except Exception as e:
                msg = str(e) if "PyMuPDF" in str(e) else "无法预览此文件"
                self._call("onPreview", {"error": msg, "data": None})

        self._start("preview", fn, overlay=False)
        return True
