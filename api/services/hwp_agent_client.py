from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_CONNECT_TIMEOUT_S = 5.0
DEFAULT_RETRIES = 2


class HwpAgentError(RuntimeError):
    """Wraps transport, HTTP, and decode errors from the local HWP agent."""


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
        with self._client() as client:
            for _ in range(self._retries):
                try:
                    resp = client.request(method, path, **kwargs)
                except httpx.HTTPError as exc:
                    last_exc = exc
                    continue
                if 200 <= resp.status_code < 300:
                    try:
                        body = resp.json()
                    except ValueError as exc:
                        raise HwpAgentError(f"invalid JSON from {path}: {exc}") from exc
                    if not isinstance(body, dict):
                        raise HwpAgentError(f"unexpected response shape from {path}")
                    return body
                # 4xx is not retryable
                if 400 <= resp.status_code < 500:
                    raise HwpAgentError(
                        f"{method} {path} -> {resp.status_code}: {resp.text[:500]}"
                    )
                last_exc = RuntimeError(f"{method} {path} -> {resp.status_code}")
        raise HwpAgentError(f"{method} {path} failed after retries: {last_exc}")

    def health(self) -> bool:
        try:
            body = self._request("GET", "/health")
        except HwpAgentError:
            return False
        return bool(body.get("ok"))

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
        return AutofillOutcome(
            template_path=str(body.get("template_path", template_path)),
            output_path=str(body.get("output_path", output_path)),
            placeholders=list(body.get("placeholders") or []),
            replaced=list(body.get("replaced") or []),
            missing=list(body.get("missing") or []),
            remaining_placeholders=list(body.get("remaining_placeholders") or []),
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
        return ProposalComposeOutcome(
            output_path=str(body.get("output_path") or output_path),
            replaced=list(body.get("replaced") or []),
            missing=list(body.get("missing") or []),
            remaining_placeholders=list(body.get("remaining_placeholders") or []),
            section_count=int(body.get("section_count") or len(sections)),
            table_count=int(body.get("table_count") or len(tables)),
            raw=body,
        )
