from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import uvicorn

from api.hwp_worker.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Local autoJEBI HWP Worker")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check", action="store_true", help="Read-only Hancom registration check")
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument("--recovery-status", action="store_true")
    recovery.add_argument("--confirm-recovery", action="store_true")
    parser.add_argument("--expected-marker-sha256", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(override=False)
    if args.check:
        from api.hwp_worker.com_driver import ComDriver

        print(json.dumps(ComDriver.availability()))
        return
    if args.recovery_status or args.confirm_recovery:
        from api.hwp_worker.recovery import RecoveryGuard, RecoveryRequired, acknowledge

        workspace = Path(os.getenv("WORKSPACE_DATA_DIR", "data/workspace"))
        root = Path(os.getenv("HWP_OUTPUT_ROOT", str(workspace / "exports")))
        try:
            guard = RecoveryGuard(root)
            if args.confirm_recovery:
                acknowledge(root, args.expected_marker_sha256, args.note)
                print(json.dumps({"recovery_acknowledged": True}))
            else:
                status = {"recovery_required": not guard.available()}
                if status["recovery_required"]:
                    if guard.marker.is_symlink() or guard.marker.stat().st_size > 16_384:
                        raise RecoveryRequired("invalid_marker")
                    status["marker_sha256"] = hashlib.sha256(guard.marker.read_bytes()).hexdigest()
                print(json.dumps(status))
        except (OSError, RecoveryRequired):
            parser.exit(2, "Recovery refused. Check marker, stopped Worker, expected hash and note.\n")
        return
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    # Load local settings without printing secrets; never expose this COM service externally.
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
