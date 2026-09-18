"""Architecture fitness functions (ADR 0001, refactor pipeline stage 9).

Import direction is enforced by import-linter (`lint-imports`). This file holds the checks that
import-linter cannot express.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Function-local first-party imports usually hide an import cycle. Budgets may only go down:
# lower the number (or delete the entry) when a cycle is removed; never raise it.
# Snapshot after R3 (2026-09-18): 31 total, down from 67 before R3.
LOCAL_IMPORT_BUDGET = {
    "api/workspace/apply.py": 1,  # specifications.service <-> workspace.service
    "api/workspace/assets.py": 2,
    "api/workspace/attachment_text.py": 1,
    "api/workspace/backup_audit.py": 1,
    "api/workspace/document_drafts.py": 3,
    "api/workspace/executors/__init__.py": 2,  # optional spec-search extra, heavy grading stack
    "api/workspace/hwp_layout.py": 1,
    "api/workspace/models.py": 2,
    "api/workspace/notice_forms.py": 1,
    "api/workspace/output_plan.py": 2,
    "api/workspace/quote_recovery.py": 2,
    "api/workspace/receipts.py": 3,
    "api/workspace/service.py": 7,  # notice_forms / source_needs / specifications cycles
    "api/workspace/supervisor.py": 1,
    "api/workspace/worker.py": 1,
    "api/workspace/writing_plan.py": 1,
}


def _local_first_party_imports(path: Path) -> int:
    count = 0
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.ImportFrom) and (sub.module or "").startswith("api"):
                count += 1
            elif isinstance(sub, ast.Import) and any(a.name.startswith("api") for a in sub.names):
                count += 1
    return count


def test_workspace_function_local_imports_do_not_grow():
    over = {}
    for path in sorted((ROOT / "api" / "workspace").rglob("*.py")):
        key = path.relative_to(ROOT).as_posix()
        found = _local_first_party_imports(path)
        if found > LOCAL_IMPORT_BUDGET.get(key, 0):
            over[key] = (found, LOCAL_IMPORT_BUDGET.get(key, 0))
    assert not over, (
        "Function-local api.* imports exceed budget (found, budget): "
        f"{over}. Import at module level; if that cycles, fix the dependency direction (ADR 0001)."
    )


def test_local_import_budget_has_no_stale_entries():
    for key, budget in LOCAL_IMPORT_BUDGET.items():
        path = ROOT / key
        assert path.is_file(), f"stale budget entry: {key}"
        found = _local_first_party_imports(path)
        assert found == budget, f"{key}: budget {budget} but found {found}; lower the budget"
