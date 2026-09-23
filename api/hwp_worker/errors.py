"""Sanitized errors shared by document use cases and the COM adapter."""

from __future__ import annotations


class ComDriverError(RuntimeError):
    """Only fixed error codes escape COM; never native exception descriptions."""

    def __init__(self, code: str, stage: str, *, cleanup_errors: list[str] | None = None) -> None:
        self.code = code
        self.stage = stage
        self.cleanup_errors = cleanup_errors or []
        self.lifecycle: list[str] = []
        self.verification_detail: dict[str, int] = {}
        super().__init__(f"{code} ({stage})")
