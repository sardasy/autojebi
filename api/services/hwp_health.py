"""Bounded read-only Worker diagnostics, independent from COM write retries."""

import asyncio
import json
import os
import re

import httpx

from api.services.hwp_agent_client import DEFAULT_BASE_URL

BASE = {"available": False, "recovery_required": False, "generation_verified": False}


async def diagnostics(*, transport=None, deadline: float = 3.0) -> dict:
    token = os.getenv("HWP_AGENT_TOKEN", "").strip()
    if len(token) < 32:
        return {**BASE, "code": "worker_token_missing"}
    try:
        async with asyncio.timeout(deadline), httpx.AsyncClient(
            base_url=os.getenv("HWP_AGENT_BASE_URL") or DEFAULT_BASE_URL,
            headers={"X-Agent-Token": token}, timeout=deadline, transport=transport,
        ) as client, client.stream("GET", "/health") as response:
            if response.status_code in {401, 403}:
                return {**BASE, "code": "worker_auth"}
            if response.status_code != 200:
                return {**BASE, "code": "worker_unhealthy"}
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 65_536:
                    return {**BASE, "code": "worker_invalid_health"}
            body = json.loads(data)
        if not isinstance(body, dict) or type(body.get("ok")) is not bool:
            return {**BASE, "code": "worker_invalid_health"}
        operation = body.get("operation")
        safe = {}
        if isinstance(operation, dict):
            for key in ("operation_id", "stage", "call_name", "failure_stage"):
                value = operation.get(key)
                if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
                    safe[key] = value
            elapsed = operation.get("elapsed_seconds")
            if type(elapsed) in (int, float) and 0 <= elapsed <= 604800:
                safe["elapsed_seconds"] = elapsed
        if body.get("recovery_required") is True:
            return {**BASE, "code": "worker_recovery", "recovery_required": True, "operation": safe}
        if body.get("state") == "running":
            return {**BASE, "code": "worker_running", "operation": safe}
        if body["ok"] is not True:
            return {**BASE, "code": "worker_unhealthy"}
        return {**BASE, "code": "worker_connected", "available": True,
                "generation_verified": body.get("generation_verified") is True}
    except (TimeoutError, httpx.TimeoutException):
        return {**BASE, "code": "worker_timeout"}
    except httpx.ConnectError:
        return {**BASE, "code": "worker_offline"}
    except (httpx.HTTPError, ValueError):
        return {**BASE, "code": "worker_invalid_health"}
