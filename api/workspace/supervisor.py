"""Restart a terminated worker without retrying its external operations."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
from datetime import UTC, datetime
from typing import Any

from api.workspace.receipts import atomic_json, data_root


def supervise(stop: threading.Event, spawn: Any = subprocess.Popen, lane: str = "all") -> None:
    from api.workspace.lanes import validate_lane
    validate_lane(lane)
    suffix = "" if lane == "all" else f"-{lane}"
    root = data_root()
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    restarts = 0
    child = None

    def record(state: str, exit_code: int | None = None) -> None:
        try:
            atomic_json(
                root / f"worker-supervisor{suffix}.json",
                {
                    "pid": os.getpid(),
                    "worker_pid": child.pid if child else None,
                    "state": state,
                    "restart_count": restarts,
                    "exit_code": exit_code,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
        except OSError:
            # Status telemetry must not terminate a worker whose external call may still run.
            logging.getLogger(__name__).warning("supervisor_status_write_failed")

    try:
        while not stop.is_set():
            with (
                (logs / f"worker{suffix}.stdout.log").open("ab") as stdout,
                (logs / f"worker{suffix}.stderr.log").open("ab") as stderr,
            ):
                try:
                    child = spawn(
                        [sys.executable, "-m", "api.workspace.worker"] + ([] if lane == "all" else ["--lane", lane]),
                        stdin=subprocess.DEVNULL,
                        stdout=stdout,
                        stderr=stderr,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except OSError:
                    record("start_failed")
                    restarts += 1
                    stop.wait(min(30, 2 ** min(restarts, 5)))
                    continue
                record("running")
                while child.poll() is None and not stop.wait(1):
                    pass
                if stop.is_set():
                    break
                record("restarting", child.returncode)
            restarts += 1
            stop.wait(min(30, 2 ** min(restarts, 5)))
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
        record("stopped")


def main() -> None:
    import argparse

    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", action="store_true")
    args = parser.parse_args()
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    if args.split:
        threads = [threading.Thread(target=supervise, args=(stop,), kwargs={"lane": lane})
                   for lane in ("local", "external")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    else:
        supervise(stop)


if __name__ == "__main__":
    main()
