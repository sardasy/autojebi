"""Opt-in personal credentials and independent roles for the v2 workspace."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

Role = Literal["viewer", "writer", "reviewer", "approver"]


class IdentitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    workspace_auth_enabled: bool = False
    workspace_auth_users: str = ""
    workspace_auth_registry: str = ""


class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=100)
    role: Role


class Credential(Actor):
    token_sha256: str = Field(pattern=r"^[a-f0-9]{64}$", exclude=True)
    enabled: bool = True


class IdentityResponse(BaseModel):
    enabled: bool
    actor: Actor | None


_actor: ContextVar[Actor | None] = ContextVar("workspace_actor", default=None)


def audit_details(details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Only the authenticated server context may supply audit identity."""
    result = {key: value for key, value in (details or {}).items() if key != "actor"}
    actor = _actor.get()
    if actor is not None:
        result["actor"] = actor.model_dump()
    return result


def configuration() -> IdentitySettings:
    try:
        return IdentitySettings()
    except (ValidationError, ValueError):
        raise HTTPException(503, detail={"code": "workspace_auth_config", "message": "개인 인증 설정을 확인하세요."}) from None


def registry(config: IdentitySettings) -> list[Credential]:
    try:
        if bool(config.workspace_auth_users) == bool(config.workspace_auth_registry):
            raise ValueError("Exactly one registry source is required")
        raw = config.workspace_auth_users
        if config.workspace_auth_registry:
            path = Path(config.workspace_auth_registry)
            if path.stat().st_size > 1_000_000:
                raise ValueError("Registry too large")
            raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list) or not data or len(data) > 1000:
            raise ValueError("Invalid registry")
        users = [Credential.model_validate(item) for item in data]
        if len({user.id for user in users}) != len(users) or len({user.token_sha256 for user in users}) != len(users):
            raise ValueError("Ambiguous registry")
        return users
    except (OSError, UnicodeError, ValueError, ValidationError):
        # Do not include registry contents or validation inputs in error responses/logs.
        raise HTTPException(503, detail={"code": "workspace_auth_config", "message": "개인 인증 설정을 확인하세요."}) from None


def authenticate(request: Request, config: IdentitySettings) -> Actor:
    users = registry(config)
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not re.fullmatch(r"[A-Za-z0-9._~+/=-]{32,512}", token):
        raise HTTPException(401, detail={"code": "workspace_auth_required", "message": "개인 계정으로 로그인하세요."})
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    matched = next((user for user in users if hmac.compare_digest(user.token_sha256, digest)), None)
    if matched is None or not matched.enabled:
        raise HTTPException(401, detail={"code": "workspace_auth_required", "message": "개인 인증 정보가 유효하지 않습니다."})
    return Actor(id=matched.id, name=matched.name, role=matched.role)


async def required_role(request: Request) -> Role | None:
    """Unknown mutations default to writer; review routes explicitly require their role."""
    path = request.url.path.rstrip("/")
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    if request.method == "POST" and (path == "/v2/search" or path.endswith("/spec-search")):
        return None
    if path.endswith("/source-review"):
        return "reviewer"
    if path.endswith("/review") and not re.search(r"/sections/[^/]+/review$", path):
        return "reviewer"
    if path.endswith(("/reviews", "/review", "/requirements")):
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            raise HTTPException(422, detail={"message": "검토 요청 형식을 확인하세요."}) from None
        if path.endswith("/reviews"):
            return "approver" if body.get("action") == "ready" else "reviewer"
        if path.endswith("/review"):
            return "writer" if body.get("approved") is None else "reviewer"
        if body.get("review_status", "pending") != "pending" or body.get("compliance", "unassessed") != "unassessed":
            return "reviewer"
    return "writer"


@asynccontextmanager
async def workspace_access(request: Request):
    if not (request.url.path == "/v2" or request.url.path.startswith("/v2/")):
        yield
        return
    config = configuration()
    actor = None
    if config.workspace_auth_enabled:
        actor = authenticate(request, config)
        role = await required_role(request)
        if role is not None and actor.role != role:
            raise HTTPException(403, detail={"code": "workspace_role_required", "message": {
                "writer": "작성자 권한이 필요합니다.", "reviewer": "검토자 권한이 필요합니다.",
                "approver": "최종 승인자 권한이 필요합니다.", "viewer": "조회 권한이 필요합니다.",
            }[role]})
    context_token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(context_token)


router = APIRouter()


@router.get("/identity", response_model=IdentityResponse)
def identity() -> IdentityResponse:
    return IdentityResponse(enabled=configuration().workspace_auth_enabled, actor=_actor.get())
