"""Bounded, content-free COM progress shared with the HTTP thread."""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

_local = threading.local()


def stage(name: str, call_name: str | None = None) -> None:
    tracker = getattr(_local, "tracker", None)
    if tracker is not None:
        tracker.update(name, call_name)


def failure(name: str) -> None:
    tracker = getattr(_local, "tracker", None)
    if tracker is not None:
        tracker.mark_failure(name)


class Progress:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()
        self.current: dict = {}
        self.started = 0.0
        self.uncertain = False

    def update(self, name: str, call_name: str | None = None) -> None:
        with self.lock:
            self.current.update(stage=name, call_name=call_name, stage_started_at=datetime.now(UTC).isoformat())
            # Fixed stage identifiers only, never COM error descriptions or input values.
            path = self.root / ".hwp-progress.jsonl"
            if path.is_symlink():
                raise RuntimeError("linked_progress_log")
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(self.current) + "\n")

    def mark_failure(self, name: str | None = None) -> None:
        with self.lock:
            self.uncertain = True
            self.current.setdefault("failure_stage", name or self.current.get("stage"))
            self.current.setdefault("failed_at", datetime.now(UTC).isoformat())

    @contextmanager
    def operation(self, operation_id: str):
        with self.lock:
            self.started = time.monotonic()
            self.current = {"operation_id": operation_id, "started_at": datetime.now(UTC).isoformat()}
        _local.tracker = self
        try:
            self.update("starting")
            yield
        finally:
            with self.lock:
                self.current["finished_at"] = datetime.now(UTC).isoformat()
                self.current["elapsed_seconds"] = round(time.monotonic() - self.started, 1)
            _local.tracker = None

    def snapshot(self) -> dict:
        with self.lock:
            return {**self.current, "elapsed_seconds": self.current.get("elapsed_seconds",
                    round(time.monotonic() - self.started, 1) if self.started else 0)}
