"""
tasks — 进程内后台任务注册表（本地单用户，不上 Celery）：
线程 + 内存 registry + 每书一把锁，串行化同 book 的写操作。
"""
import threading
from contextlib import contextmanager
from typing import Callable

from pipeline import store


class TaskRegistry:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._submit_lock = threading.Lock()

    def submit(self, book_id: str, target: Callable, *args) -> None:
        """起后台线程跑 target；同名任务排队等待前一个结束（daemon，进程退出即止）。"""
        # 检查 + 注册必须原子，否则两个并发重跑请求可能各起一个线程
        with self._submit_lock:
            if book_id in self._threads:
                prev = self._threads[book_id]
                if prev.is_alive():
                    raise RuntimeError(f"book {book_id} 已有任务在运行")

            def _run():
                with self.lock(book_id):
                    target(*args)

            t = threading.Thread(target=_run, name=f"task-{book_id}", daemon=True)
            self._threads[book_id] = t
            t.start()

    def join_all(self, timeout: float = 10.0) -> None:
        """等待所有任务结束（测试 / 优雅退出用）。"""
        with self._submit_lock:
            threads = list(self._threads.values())
        for t in threads:
            t.join(timeout)

    def is_running(self, book_id: str) -> bool:
        t = self._threads.get(book_id)
        return bool(t and t.is_alive())

    def status(self, book_id: str) -> dict:
        meta = store.read_meta(book_id)
        if not meta:
            return {"exists": False}
        return {**meta, "alive": self.is_running(book_id)}

    @contextmanager
    def lock(self, book_id: str):
        if book_id not in self._locks:
            self._locks[book_id] = threading.Lock()
        with self._locks[book_id]:
            yield

    def can_resynth(self, book_id: str) -> bool:
        meta = store.read_meta(book_id)
        return (meta.get("status") in ("ready", "error")) and not self.is_running(book_id)


registry = TaskRegistry()