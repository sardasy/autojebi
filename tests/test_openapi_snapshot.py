"""Refactor guardrail: the public API schema must not change during structural refactors.

Snapshot: tests/snapshots/openapi.json (refactor pipeline stage 3 guardrail, ADR 0001).
Intentional API change: regenerate with `UPDATE_OPENAPI_SNAPSHOT=1 pytest tests/test_openapi_snapshot.py`
and review the snapshot diff in the same PR.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from api.main import app

SNAPSHOT = Path(__file__).parent / "snapshots" / "openapi.json"


def _render() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def test_openapi_matches_snapshot():
    current = _render()
    if os.getenv("UPDATE_OPENAPI_SNAPSHOT") == "1":
        SNAPSHOT.write_text(current, encoding="utf-8", newline="\n")
    expected = SNAPSHOT.read_text(encoding="utf-8")
    assert current == expected, (
        "OpenAPI schema changed. If intentional, regenerate with UPDATE_OPENAPI_SNAPSHOT=1 "
        "and review tests/snapshots/openapi.json in the PR."
    )
