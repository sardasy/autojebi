from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future


class SerialQueue:
    """Own COM calls on one thread; HTTP cancellation never replays a running call."""

    def __init__(self, capacity: int = 4) -> None:
        self._items: queue.Queue = queue.Queue(maxsize=capacity)
        self._guard = threading.Lock()
        self._closed = False
        self._active = False
        self._thread = threading.Thread(target=self._run, name="hwp-com-owner", daemon=True)
        self._thread.start()

    def submit(self, operation: Callable[[], dict]) -> Future:
        future: Future = Future()
        with self._guard:
            if self._closed:
                raise RuntimeError("queue_closed")
            self._items.put_nowait((future, operation))
        return future

    def state(self) -> dict:
        with self._guard:
            return {
                "running": self._active,
                "queued": self._items.qsize(),
                "accepting": not self._closed,
            }

    def close(self) -> None:
        with self._guard:
            self._closed = True
            while True:
                try:
                    future, _ = self._items.get_nowait()
                except queue.Empty:
                    break
                future.cancel()
                self._items.task_done()

    def _run(self) -> None:
        while True:
            try:
                future, operation = self._items.get(timeout=0.1)
            except queue.Empty:
                with self._guard:
                    if self._closed:
                        return
                continue
            with self._guard:
                proceed = not self._closed and future.set_running_or_notify_cancel()
                if not proceed and not future.cancelled():
                    future.cancel()
                self._active = proceed
            try:
                if proceed:
                    try:
                        future.set_result(operation())
                    except Exception as exc:
                        future.set_exception(exc)
            finally:
                with self._guard:
                    self._active = False
                self._items.task_done()
