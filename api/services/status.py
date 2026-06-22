from __future__ import annotations

FINAL_STATUSES = {"notified", "digest_queued", "archived_low"}

PROCESSING_STATUSES = [
    "collected",
    "analyzed",
    "attachments_fetched",
    "documents_analyzed",
    "spec_extracted",
    "hwp_composed",
    "form_filled",
]

# Intermediate states that sit between `analyzed` and the final notify states.
INTERMEDIATE_STATUSES = set(PROCESSING_STATUSES) - {"collected", "analyzed"}
STATUS_ORDER = {status: idx for idx, status in enumerate(PROCESSING_STATUSES)}


def compute_notify_status(fit_score: int) -> str:
    if fit_score >= 70:
        return "notified"
    if fit_score >= 40:
        return "digest_queued"
    return "archived_low"


def can_transition(current_status: str, next_status: str) -> bool:
    current = (current_status or "").strip()
    nxt = (next_status or "").strip()
    if not current:
        return nxt == "collected"
    if current in FINAL_STATUSES:
        return False
    if nxt in FINAL_STATUSES:
        return current in STATUS_ORDER and STATUS_ORDER[current] >= STATUS_ORDER["analyzed"]
    if current == "collected":
        return nxt == "analyzed"
    if current not in STATUS_ORDER or nxt not in STATUS_ORDER:
        return False
    return STATUS_ORDER[nxt] > STATUS_ORDER[current]


def advance_status(current_status: str, target_status: str) -> str:
    """Return target only when it moves the pipeline forward."""
    current = (current_status or "").strip()
    target = (target_status or "").strip()
    if current in FINAL_STATUSES:
        return current
    if not current:
        return target if target == "collected" else current
    if target in FINAL_STATUSES:
        return target if can_transition(current, target) else current
    if current not in STATUS_ORDER or target not in STATUS_ORDER:
        return current
    return target if STATUS_ORDER[target] > STATUS_ORDER[current] else current
