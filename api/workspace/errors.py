"""v2 domain errors (ADR 0001).

Domain code raises ``WorkspaceError`` instead of FastAPI's ``HTTPException``; the router layer
maps it to the same ``{"detail": ...}`` response via ``install_error_handlers``.

This is the only ``api.workspace`` module (besides the HTTP adapter ``identity``) allowed to
import fastapi: legacy services (``api.services.uploads``/``exporters``, ``api.db``) still raise
``HTTPException``, so catch sites use ``HANDLED_ERRORS`` until those services are migrated.
"""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import HTTPException


class WorkspaceError(Exception):
    """Domain error with an HTTP-compatible status and structured detail."""

    def __init__(self, status_code: int, detail: Any = None) -> None:
        super().__init__(status_code, detail)
        self.status_code = status_code
        self.detail = detail
        self.headers: dict[str, str] | None = None

    def __str__(self) -> str:
        return f"{self.status_code}: {self.detail}"


def fail(
    code: str, message: str, next_action: str = "입력과 최신 상태를 확인하세요.", status: int = 409
) -> NoReturn:
    """Raise the standard v2 error (``detail`` = code/message/next_action/job_id)."""
    raise WorkspaceError(
        status,
        {"code": code, "message": message, "next_action": next_action, "job_id": None},
    )


# Transitional: legacy services still raise HTTPException (see module docstring).
HANDLED_ERRORS: tuple[type[Exception], ...] = (WorkspaceError, HTTPException)
HandledError = WorkspaceError | HTTPException
