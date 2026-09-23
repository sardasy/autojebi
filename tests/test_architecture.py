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
    "api/workspace/backup_audit.py": 1,
    "api/workspace/document_drafts.py": 3,
    "api/workspace/executors/__init__.py": 2,  # optional spec-search extra, heavy grading stack
    "api/workspace/hwp_layout.py": 1,
    "api/workspace/models.py": 2,
    "api/workspace/output_plan.py": 2,
    "api/workspace/quote_recovery.py": 2,
    "api/workspace/receipts.py": 3,
    "api/workspace/service.py": 4,
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


# ADR 0001 FF 3: LLM clients are created only on the v2 provider path, where call limits and
# reuse are recorded (AGENTS.md §1). The v1 call sites are frozen: remove entries, never add.
ANTHROPIC_CLIENT_ALLOWED = {
    "api/workspace/anthropic_client.py",  # v2, behind api/workspace/providers.py
    "api/grading/summarizer.py",  # v1 (frozen)
    "api/llm/extractor.py",  # v1 (frozen)
    "api/services/document_automation.py",  # v1 (frozen)
    "api/services/mail_extractor.py",  # v1 (frozen)
    "api/services/required_documents.py",  # v1 (frozen)
}


def _creates_anthropic_client(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"Anthropic", "AsyncAnthropic"}:
                return True
    return False


def test_anthropic_clients_only_on_allowed_paths():
    found = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "api").rglob("*.py")
        if _creates_anthropic_client(path)
    }
    assert found <= ANTHROPIC_CLIENT_ALLOWED, (
        f"New Anthropic client construction outside providers: {sorted(found - ANTHROPIC_CLIENT_ALLOWED)}. "
        "Use api.workspace.providers.prepare_request/generate."
    )
    assert found == ANTHROPIC_CLIENT_ALLOWED, (
        f"Allowlist entries no longer create a client; delete them: {sorted(ANTHROPIC_CLIENT_ALLOWED - found)}"
    )


# ADR 0001 FF 4: file size caps. Existing oversize files may only shrink (budget = current size);
# new or other files must stay under the caps. TS/TSX also has a byte cap because very long JSX
# lines hid a 63 KB component behind 496 lines.
PY_MAX_LINES = 600
TS_MAX_LINES = 300
TS_MAX_BYTES = 24_000
SIZE_BUDGET: dict[str, int | tuple[int, int]] = {
    "api/routers/notices.py": 3049,
    "api/specifications/table_structure.py": 818,
    "api/workspace/service.py": 694,
    "api/models/notices.py": 715,
    "api/specifications/retrieval.py": 689,
    "api/routers/workspace.py": 655,
    "api/services/document_automation.py": 608,
    "frontend/src/components/DocumentPreparationPanel.tsx": (656, 27184),
    "frontend/src/components/HwpComposeDialog.tsx": (405, 17687),
    "frontend/src/components/HwpMappingAdmin.tsx": (527, 19245),
    "frontend/src/components/ProposalComposeDialog.tsx": (344, 14734),
    "frontend/src/components/SpecificationWorkbench.tsx": (353, 23950),
    "frontend/src/lib/actions.ts": (327, 9863),
    "frontend/src/lib/api.ts": (1323, 36524),
}


def _measured_sizes() -> dict[str, int | tuple[int, int]]:
    sizes: dict[str, int | tuple[int, int]] = {}
    for path in (ROOT / "api").rglob("*.py"):
        sizes[path.relative_to(ROOT).as_posix()] = len(path.read_text(encoding="utf-8").splitlines())
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if path.suffix in {".ts", ".tsx"} and "__tests__" not in path.parts:
            text = path.read_text(encoding="utf-8")
            sizes[path.relative_to(ROOT).as_posix()] = (len(text.splitlines()), len(text.encode()))
    return sizes


def _over_cap(size: int | tuple[int, int]) -> bool:
    if isinstance(size, tuple):
        return size[0] > TS_MAX_LINES or size[1] > TS_MAX_BYTES
    return size > PY_MAX_LINES


def test_source_files_stay_within_size_budget():
    violations = {}
    for key, size in _measured_sizes().items():
        budget = SIZE_BUDGET.get(key)
        if budget is None:
            if _over_cap(size):
                violations[key] = (size, "cap")
        elif isinstance(size, tuple) and isinstance(budget, tuple):
            if size[0] > budget[0] or size[1] > budget[1]:
                violations[key] = (size, budget)
        elif size > budget:
            violations[key] = (size, budget)
    assert not violations, (
        f"Files over the size cap or budget (found, allowed): {violations}. Split the module (ADR 0001)."
    )


def test_size_budget_has_no_stale_entries():
    sizes = _measured_sizes()
    for key, budget in SIZE_BUDGET.items():
        assert key in sizes, f"stale size budget entry: {key}"
        assert _over_cap(sizes[key]), f"{key} is now under the cap; delete its budget entry"
        assert sizes[key] == budget, f"{key}: budget {budget} but found {sizes[key]}; lower the budget"
