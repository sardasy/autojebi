from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_CONNECT_TIMEOUT_S = 5.0
DEFAULT_RETRIES = 2


class HwpAgentError(RuntimeError):
    """Wraps transport, HTTP, and decode errors from the local HWP agent."""

    def __init__(self, message: str, *, code: str = "worker_error", stage: str | None = None):
        self.code = code
        self.stage = stage
        super().__init__(message)


class _FieldsResponse(BaseModel):
    # Extension metadata is allowed, but required reports must never be synthesized.
    model_config = ConfigDict(strict=True, extra="allow")

    output_path: str = Field(min_length=1)
    replaced: list[str]
    missing: list[str]
    remaining_placeholders: list[str]
    fields: list[str] | None = None

    @field_validator("output_path")
    @classmethod
    def nonblank_path(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("invalid output path")
        return value

    @field_validator("replaced", "missing", "remaining_placeholders", "fields")
    @classmethod
    def field_names(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (
            any(not name.strip() or "\x00" in name for name in value)
            or len(value) != len(set(value))
        ):
            raise ValueError("invalid or duplicate field names")
        return value


class _AutofillResponse(_FieldsResponse):
    template_path: str = Field(min_length=1)
    placeholders: list[str]


class _ProposalResponse(_FieldsResponse):
    section_count: Annotated[int, Field(ge=0)]
    table_count: Annotated[int, Field(ge=0)]


class _FieldOccurrence(BaseModel):
    model_config = ConfigDict(strict=True)
    field: str = Field(min_length=1, max_length=200)
    occurrence: int = Field(ge=0)


class _InspectionResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fields: list[str] = Field(max_length=10000)
    field_occurrences: list[_FieldOccurrence] = Field(max_length=10000)
    lifecycle: list[str]


_Response = TypeVar("_Response", bound=_FieldsResponse)


def _reject_provider_error(body: dict[str, Any]) -> None:
    if (
        any(key in body and body[key] is not True for key in ("ok", "success"))
        or body.get("error") not in (None, "", [], {})
        or body.get("errors") not in (None, "", [], {})
        or str(body.get("status", "")).lower() in {"error", "failed", "failure", "blocked"}
    ):
        # Never include provider payloads: errors can contain document text or credentials.
        raise HwpAgentError("HWP provider reported an error")


def _parse_response(body: dict[str, Any], schema: type[_Response]) -> _Response:
    _reject_provider_error(body)
    try:
        return schema.model_validate(body)
    except ValidationError:
        raise HwpAgentError("invalid HWP provider response schema") from None


def validate_put_fields_response(
    body: dict[str, Any], expected_fields: list[str]
) -> _FieldsResponse:
    """Validate reports, not saved field values or COM execution guarantees.

    Every requested field must be reported exactly once as replaced or missing.
    Additional missing template fields are retained as draft warnings.
    """
    report = _parse_response(body, _FieldsResponse)
    expected, replaced, missing = set(expected_fields), set(report.replaced), set(report.missing)
    if replaced & missing or replaced - expected or expected - (replaced | missing):
        raise HwpAgentError("inconsistent HWP provider field partition")
    return report


@dataclass(frozen=True)
class AutofillOutcome:
    template_path: str
    output_path: str
    placeholders: list[str]
    replaced: list[str]
    missing: list[str]
    remaining_placeholders: list[str]
    raw: dict[str, Any]


@dataclass(frozen=True)
class ProposalComposeOutcome:
    output_path: str
    replaced: list[str]
    missing: list[str]
    remaining_placeholders: list[str]
    section_count: int
    table_count: int
    raw: dict[str, Any]


@dataclass(frozen=True)
class PutFieldsOutcome:
    output_path: str
    replaced: list[str]
    missing: list[str]
    remaining_placeholders: list[str]
    raw: dict[str, Any]


class HwpAgentClient:
    """Thin httpx wrapper around the local milim-hwp-agent FastAPI service.

    Connect/read timeouts are conservative because HWP COM calls (open/save)
    can take several seconds on first launch. Two attempts total; failures
    raise HwpAgentError so the caller can decide whether to fail the route
    or record into bid_pipeline.analysis.errors.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
        retries: int = DEFAULT_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("HWP_AGENT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._token = (token or os.getenv("HWP_AGENT_TOKEN") or "").strip()
        self._timeout = httpx.Timeout(timeout_s, connect=connect_timeout_s)
        self._retries = max(1, retries)
        self._transport = transport

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._token:
            headers["X-Agent-Token"] = self._token
        return headers

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "base_url": self._base_url,
            "timeout": self._timeout,
            "headers": self._headers(),
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        last_exc: Exception | None = None
        connect_failed = False
        with self._client() as client:
            # A timed-out COM write may still be saving. Only read-only HTTP calls can retry.
            attempts = self._retries if method.upper() == "GET" else 1
            for _ in range(attempts):
                try:
                    resp = client.request(method, path, **kwargs)
                except httpx.HTTPError as exc:
                    last_exc = exc
                    # 연결 자체가 안 되는 경우(에이전트 미실행 등)는 별도 분류 →
                    # 호출자에게 "[Errno 101] Network is unreachable" 대신 actionable 메시지 제공.
                    connect_failed = isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout)
                    continue
                if 200 <= resp.status_code < 300:
                    try:
                        body = resp.json()
                    except ValueError as exc:
                        raise HwpAgentError(f"invalid JSON from {path}: {exc}") from exc
                    if not isinstance(body, dict):
                        raise HwpAgentError(f"unexpected response shape from {path}")
                    _reject_provider_error(body)
                    return body
                if method.upper() != "GET" or 400 <= resp.status_code < 500:
                    try:
                        detail = resp.json().get("detail", {})
                        code = detail.get("code", "worker_error") if isinstance(detail, dict) else "worker_error"
                        stage = detail.get("stage") if isinstance(detail, dict) else None
                        if not isinstance(code, str) or not re.fullmatch(r"[a-z_]{1,80}", code):
                            code = "worker_error"
                        if not isinstance(stage, str) or not re.fullmatch(r"[a-z_]{1,80}", stage):
                            stage = None
                    except ValueError:
                        code, stage = "worker_error", None
                    raise HwpAgentError(f"HWP Worker 요청 실패 (HTTP {resp.status_code}): {code}", code=code, stage=stage)
                last_exc = RuntimeError(f"{method} {path} -> {resp.status_code}")
        if connect_failed:
            raise HwpAgentError(
                f"HWP 에이전트에 연결할 수 없습니다 ({self._base_url}). "
                f"데스크톱 에이전트 실행 여부를 확인하세요. (원인: {last_exc})"
            )
        raise HwpAgentError(f"{method} {path} failed after retries: {last_exc}")

    def health(self) -> bool:
        try:
            body = self._request("GET", "/health")
        except HwpAgentError:
            return False
        return body.get("ok") is True

    def diagnostics(self) -> dict[str, Any]:
        """Read-only, single attempt. Never return provider text, paths, or credentials."""
        result = {"available": False, "code": "worker_offline", "recovery_required": False,
                  "generation_verified": False}
        if len(self._token) < 32:
            return {**result, "code": "worker_token_missing"}
        try:
            with self._client() as client:
                response = client.get("/health")
            if response.status_code in {401, 403}:
                return {**result, "code": "worker_auth"}
            if response.status_code != 200:
                return result
            body = response.json()
            if not isinstance(body, dict):
                return {**result, "code": "worker_invalid_health"}
            operation = body.get("operation")
            safe_operation = {}
            if isinstance(operation, dict):
                for key in ("operation_id", "stage", "call_name", "failure_stage"):
                    value = operation.get(key)
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
                        safe_operation[key] = value
                elapsed = operation.get("elapsed_seconds")
                if type(elapsed) in (int, float) and 0 <= elapsed <= 604800:
                    safe_operation["elapsed_seconds"] = elapsed
                for key in ("started_at", "stage_started_at", "failed_at", "finished_at"):
                    value = operation.get(key)
                    if isinstance(value, str) and re.fullmatch(r"[0-9T:.+Z-]{1,40}", value):
                        safe_operation[key] = value
            if body.get("recovery_required") is True:
                return {**result, "code": "worker_recovery", "recovery_required": True, "operation": safe_operation}
            if body.get("state") == "running":
                return {**result, "code": "worker_running", "operation": safe_operation}
            if body.get("ok") is not True:
                return {**result, "code": "worker_unhealthy"}
            return {**result, "available": True, "code": "worker_connected",
                    "generation_verified": body.get("generation_verified") is True}
        except httpx.TimeoutException:
            return {**result, "code": "worker_timeout"}
        except (httpx.HTTPError, ValueError):
            return result

    def create_template(self, *, operation_id: str, output_path: str, layout: dict,
                        base_template_path: str | None = None, visible: bool = False) -> dict:
        return self._request("POST", "/document/create-template", json={
            "operation_id": operation_id, "output_path": output_path, "layout": layout,
            "base_template_path": base_template_path, "visible": visible,
        })

    def autofill_bid_form(
        self,
        *,
        template_path: str,
        output_path: str,
        values: dict[str, str],
        visible: bool = False,
    ) -> AutofillOutcome:
        payload = {
            "template_path": template_path,
            "output_path": output_path,
            "values": values,
            "visible": visible,
        }
        body = self._request("POST", "/bid-form/autofill", json=payload)
        report = _parse_response(body, _AutofillResponse)
        return AutofillOutcome(
            template_path=report.template_path,
            output_path=report.output_path,
            placeholders=report.placeholders,
            replaced=report.replaced,
            missing=report.missing,
            remaining_placeholders=report.remaining_placeholders,
            raw=body,
        )

    def rag_search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        body = self._request("POST", "/rag/search", json={"query": query, "limit": limit})
        results = body.get("results") or []
        return [r for r in results if isinstance(r, dict)]

    def analyze_document(self, path: str) -> dict[str, Any]:
        """Calls milim-hwp-agent's stateless file analyzer (M1 addition)."""
        body = self._request("POST", "/document/analyze-file", json={"path": path})
        return body

    def inspect_fields(self, path: str, *, visible: bool = False, operation_id: str | None = None) -> dict[str, Any]:
        payload = {"path": path}
        if visible:
            payload["visible"] = True
        if operation_id:
            payload["operation_id"] = operation_id
        body = self._request("POST", "/document/fields", json=payload)
        try:
            report = _InspectionResponse.model_validate(body)
            if report.lifecycle not in (["opened", "closed", "quit"], ["opened", "readback", "closed", "quit"]):
                raise ValueError("incomplete lifecycle")
            counts: dict[str, int] = {}
            for item in report.field_occurrences:
                if not item.field.strip() or any(c in item.field for c in ("\x00", "\x02", "{{", "}}")):
                    raise ValueError("invalid field")
                if item.occurrence != counts.get(item.field, 0):
                    raise ValueError("invalid occurrence")
                counts[item.field] = item.occurrence + 1
            if report.fields != list(counts):
                raise ValueError("inconsistent names")
            return report.model_dump()
        except (ValidationError, ValueError):
            raise HwpAgentError("invalid HWP field inspection report") from None

    def generate_compliance_table(
        self,
        *,
        output_path: str,
        title: str,
        headers: list[str],
        rows: list[list[str]],
    ) -> dict[str, Any]:
        """milim-hwp-agent의 ``/document/insert-table`` 호출로 .hwp 생성 (M11).

        에이전트가 해당 엔드포인트를 구현하지 않으면 4xx/5xx → ``HwpAgentError``.
        ``api/services/exporters.py``의 ``build_hwp``가 이를 ``ExportError(502)``로 변환.

        요청 body:
            ``{ output_path, title, table: { headers: [...], rows: [[...]] } }``
        응답 body:
            ``{ output_path, sheet_count?, ... }``
        """
        payload = {
            "output_path": output_path,
            "title": title,
            "table": {"headers": headers, "rows": rows},
        }
        return self._request("POST", "/document/insert-table", json=payload)

    def compose_proposal(
        self,
        *,
        template_path: str,
        output_path: str,
        values: dict[str, str],
        sections: list[dict[str, str]],
        tables: list[dict[str, Any]],
        visible: bool = False,
    ) -> ProposalComposeOutcome:
        payload = {
            "template_path": template_path,
            "output_path": output_path,
            "values": values,
            "sections": sections,
            "tables": tables,
            "visible": visible,
        }
        body = self._request("POST", "/proposal/compose", json=payload)
        report = _parse_response(body, _ProposalResponse)
        return ProposalComposeOutcome(
            output_path=report.output_path,
            replaced=report.replaced,
            missing=report.missing,
            remaining_placeholders=report.remaining_placeholders,
            section_count=report.section_count,
            table_count=report.table_count,
            raw=body,
        )

    def put_fields(
        self,
        *,
        template_path: str,
        output_path: str,
        values: dict[str, str],
        visible: bool = False,
        operation_id: str | None = None,
        render_pages: bool = False,
    ) -> PutFieldsOutcome:
        """Fill HWP fields through the worker's serialized PutFieldText endpoint."""
        payload = {
            "template_path": template_path,
            "output_path": output_path,
            "values": values,
            "visible": visible,
        }
        if operation_id is not None:
            payload["operation_id"] = operation_id
        if render_pages:
            payload["render_pages"] = True
        body = self._request("POST", "/document/put-fields", json=payload)
        report = validate_put_fields_response(body, list(values))
        return PutFieldsOutcome(
            output_path=report.output_path,
            replaced=report.replaced,
            missing=report.missing,
            remaining_placeholders=report.remaining_placeholders,
            raw=body,
        )
