"""后台任务线程池（并发层核心）。

设计要点：
1. 所有阻塞操作（网络连接、列目录、上传下载、PDF 渲染）都通过 submit() 跑在
   独立的守护线程里，主线程（Tkinter 事件循环）只负责 UI，因此界面永远不会卡死/转圈。
2. 任务函数统一签名：fn(progress, cancel, *args, **kwargs)
   - progress(pct: float, msg: str) 上报进度
   - cancel 是 threading.Event 的包装（TaskHandle），调用 cancel.is_cancelled() 查询
3. 回调（on_done / on_error / on_progress）一律通过 root.after(0, ...) 切回主线程执行，
   因而可以安全地操作任何 Tk 控件。
4. 支持用 task_id 取消正在进行的任务（cancel(task_id)）。
"""

import threading
from typing import Any, Callable, Optional


class Cancelled(Exception):
    """任务被用户取消时抛出。"""


class TaskHandle:
    """单个任务的取消令牌。"""

    def __init__(self):
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()


class WorkerPool:
    def __init__(self, root):
        self._root = root
        self._seq = 0
        self._tasks: dict[str, TaskHandle] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        fn: Callable,
        *,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        on_done: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Any], None]] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        task_id: Optional[str] = None,
    ) -> TaskHandle:
        """提交一个后台任务。返回 TaskHandle（可调用 .cancel() 取消）。"""
        kwargs = kwargs or {}
        handle = TaskHandle()
        tid = task_id or f"task-{self._seq}"
        self._seq += 1
        with self._lock:
            self._tasks[tid] = handle

        def progress(pct: float = 0.0, msg: str = "") -> None:
            if on_progress:
                self._to_main(on_progress, pct, msg)

        def run() -> None:
            try:
                result = fn(progress, handle, *args, **kwargs)
            except Cancelled:
                if on_error:
                    self._to_main(on_error, "已取消")
                return
            except Exception as e:  # 捕获一切，避免线程静默崩溃
                if on_error:
                    self._to_main(on_error, e)
                return
            finally:
                with self._lock:
                    self._tasks.pop(tid, None)
            if on_done:
                self._to_main(on_done, result)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return handle

    def cancel(self, task_id: str) -> None:
        with self._lock:
            h = self._tasks.get(task_id)
        if h:
            h.cancel()

    def _to_main(self, cb: Callable, *args) -> None:
        try:
            self._root.after(0, lambda: cb(*args))
        except Exception:
            pass
