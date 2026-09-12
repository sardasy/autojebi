"""Single-attempt structured generation; never log provider bodies or credentials."""

import json
import re
from typing import Any

import httpx

from api.config import settings
from api.workspace.service import fail


def prepare_request(request: dict) -> dict:
    if settings.workspace_llm_provider != "gemini":
        return request
    model = settings.gemini_model.strip()
    if not re.fullmatch(r"gemini-[A-Za-z0-9._-]+", model):
        fail("llm_model_invalid", "Gemini 모델 설정이 올바르지 않습니다.", "GEMINI_MODEL을 확인하세요.")
    return {
        "provider": "gemini",
        "model": model,
        "payload": {
            "systemInstruction": {"parts": [{"text": request["system"]}]},
            "contents": [
                {"role": "user", "parts": [{"text": m["content"]}]}
                for m in request["messages"]
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": request["tools"][0]["input_schema"],
                "maxOutputTokens": settings.gemini_max_output_tokens,
                "candidateCount": 1,
            },
        },
    }


def generate(request: dict) -> dict:
    key = settings.google_api_key.strip()
    if not key:
        fail("llm_not_configured", "Google API 키가 등록되지 않았습니다.", "로컬 .env의 GOOGLE_API_KEY를 등록하고 API와 작업 실행기를 재시작하세요.")
    try:
        with httpx.Client(timeout=180, follow_redirects=False) as client:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{request['model']}:generateContent",
                headers={"x-goog-api-key": key},
                json=request["payload"],
            )
    except httpx.TimeoutException:
        fail("llm_timeout", "Gemini 응답 시간이 초과되었습니다.", "실행 이력과 호출 한도를 확인하세요. 자동 재시도하지 않습니다.", status=504)
    except httpx.RequestError:
        fail("llm_connection_failed", "Gemini에 연결하지 못했습니다.", "인터넷 연결과 방화벽을 확인하세요.", status=502)
    invalid_key = False
    if response.status_code == 400:
        try:
            invalid_key = any(
                d.get("reason") in {"API_KEY_INVALID", "API_KEY_EXPIRED"}
                for d in response.json().get("error", {}).get("details", [])
            )
        except (ValueError, AttributeError, TypeError):
            pass
    if response.status_code in {401, 403} or invalid_key:
        fail("llm_authentication_failed", "Google API 인증 또는 사용 권한을 확인하지 못했습니다.", "Google API 키와 Gemini API 사용 권한을 확인하세요.", status=502)
    if response.status_code == 429:
        fail("llm_rate_limited", "Gemini 사용량 또는 결제 한도에 도달했습니다.", "Google 프로젝트의 할당량과 결제 상태를 확인하세요.", status=503)
    if response.status_code == 404:
        fail("llm_model_unavailable", "설정된 Gemini 모델을 사용할 수 없습니다.", "GEMINI_MODEL과 해당 프로젝트의 모델 사용 권한을 확인하세요.", status=502)
    if response.status_code != 200:
        fail("llm_provider_error", f"Gemini가 요청을 처리하지 못했습니다. (HTTP {response.status_code})", "모델 설정과 Google 서비스 상태를 확인하세요.", status=502)
    try:
        body = response.json()
        if (body.get("promptFeedback") or {}).get("blockReason"):
            fail("llm_response_blocked", "Gemini가 입력 처리를 차단했습니다.", "원문 내용을 확인하세요. 자동 재시도하지 않습니다.", status=502)
        candidates = body["candidates"]
        if len(candidates) == 1:
            reason = candidates[0].get("finishReason")
            if reason == "MAX_TOKENS":
                fail("llm_output_limit", "Gemini 응답이 출력 길이 한도에 도달했습니다.", "잘린 결과는 반영하지 않습니다. GEMINI_MAX_OUTPUT_TOKENS와 남은 호출 한도를 확인하세요.", status=502)
            if reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
                fail("llm_response_blocked", "Gemini가 응답 제공을 제한했습니다.", "원문 내용과 Google 정책을 확인하세요. 자동 재시도하지 않습니다.", status=502)
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            fail("llm_incomplete_response", "Gemini 응답이 완료되지 않았습니다.", "잘린 결과는 저장하지 않습니다. 실행 이력을 확인하세요.", status=502)
        parts = candidates[0]["content"]["parts"]
        value: Any = json.loads("".join(p["text"] for p in parts if not p.get("thought")))
        if not isinstance(value, dict):
            raise ValueError("Expected an object")
        return value
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        fail("invalid_llm_response", "Gemini 응답 형식을 확인하지 못했습니다.", "분석 결과는 반영하지 않았습니다. 실행 이력을 확인하세요.", status=502)
