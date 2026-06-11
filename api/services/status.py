from __future__ import annotations

FINAL_STATUSES = {"notified", "digest_queued", "archived_low"}

# Intermediate states that sit between `analyzed` and the final notify states.
# `form_filled` is reached after milim-hwp-agent autofills the bid form template.
INTERMEDIATE_STATUSES = {"form_filled"}


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
    if current == "collected":
        return nxt == "analyzed"
    if current == "analyzed":
        return nxt in FINAL_STATUSES or nxt == "form_filled"
    if current == "form_filled":
        return nxt in FINAL_STATUSES
    return False

