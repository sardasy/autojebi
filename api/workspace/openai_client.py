"""Stateless, single-attempt Responses API generation with validated JSON output."""

import json
import re
from copy import deepcopy

import httpx

from api.config import settings
from api.workspace.service import fail


def strict_schema(schema: dict) -> dict:
    result = deepcopy(schema)

    def visit(node: dict) -> None:
        if node.get("type") == "object":
            properties = node.get("properties", {})
            if set(node.get("required", [])) != set(properties):
                fail("llm_schema_invalid", "OpenAI 출력 스키마의 필수 항목 설정을 확인하세요.")
            node["additionalProperties"] = False
        for key in ("properties", "$defs"):
            for child in node.get(key, {}).values():
                visit(child)
        if isinstance(node.get("items"), dict):
            visit(node["items"])
        for key in ("anyOf", "oneOf", "allOf"):
            for child in node.get(key, []):
                visit(child)

    visit(result)
    return result


def prepare_request(request: dict) -> dict:
    model = settings.openai_model.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model):
        fail("llm_model_invalid", "OpenAI 모델 설정이 올바르지 않습니다.", "OPENAI_MODEL을 확인하세요.")
    tool = request["tools"][0]
    return {
        "provider": "openai",
        "model": model,
        "payload": {
            "model": model,
            "instructions": request["system"],
            "input": request["messages"],
            "text": {"format": {
                "type": "json_schema", "name": tool["name"], "strict": True,
                "schema": strict_schema(tool["input_schema"]),
            }},
            "max_output_tokens": settings.openai_max_output_tokens,
            "store": False,
        },
    }


def generate(request: dict) -> dict:
    key = settings.openai_api_key.strip()
    if not key:
        fail("llm_not_configured", "OpenAI API 키가 등록되지 않았습니다.", "로컬 .env의 OPENAI_API_KEY를 등록하고 API와 작업 실행기를 재시작하세요.")
    try:
        with httpx.Client(timeout=180, follow_redirects=False) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {key}"},
                json=request["payload"],
            )
    except httpx.TimeoutException:
        fail("llm_timeout", "OpenAI 응답 시간이 초과되었습니다.", "작업 이력과 남은 호출 한도를 확인하세요. 자동 재시도하지 않습니다.", status=504)
    except httpx.RequestError:
        fail("llm_connection_failed", "OpenAI에 연결하지 못했습니다.", "인터넷 연결과 방화벽을 확인하세요.", status=502)
    if response.status_code in {401, 403}:
        fail("llm_authentication_failed", "OpenAI 인증 또는 사용 권한을 확인하지 못했습니다.", "OpenAI 프로젝트의 키와 사용 권한을 확인하세요.", status=502)
    if response.status_code == 429:
        fail("llm_rate_limited", "OpenAI 사용량 또는 결제 한도에 도달했습니다.", "API 프로젝트의 결제·할당량을 확인하세요.", status=503)
    if response.status_code == 404:
        fail("llm_model_unavailable", "설정된 OpenAI 모델을 사용할 수 없습니다.", "OPENAI_MODEL과 프로젝트의 모델 권한을 확인하세요.", status=502)
    if response.status_code != 200:
        fail("llm_provider_error", f"OpenAI가 요청을 처리하지 못했습니다. (HTTP {response.status_code})", "모델·출력 설정과 OpenAI 서비스 상태를 확인하세요.", status=502)
    try:
        body = response.json()
        if body.get("status") == "incomplete":
            reason = (body.get("incomplete_details") or {}).get("reason")
            if reason == "max_output_tokens":
                fail("llm_output_limit", "OpenAI 응답이 출력 길이 한도에 도달했습니다.", "잘린 결과는 반영하지 않습니다. OPENAI_MAX_OUTPUT_TOKENS와 남은 호출 한도를 확인하세요.", status=502)
            fail("llm_incomplete_response", "OpenAI 응답이 완료되지 않았습니다.", "원문과 실행 이력을 확인하세요.", status=502)
        if body.get("error") or body.get("status") != "completed":
            fail("llm_provider_error", "OpenAI 작업이 정상 완료되지 않았습니다.", "실행 이력을 확인하세요. 자동 재시도하지 않습니다.", status=502)
        texts = []
        for item in body["output"]:
            if item.get("type") != "message":
                continue
            if item.get("role") != "assistant" or item.get("status") != "completed":
                fail("llm_incomplete_response", "OpenAI 결과 메시지가 완료되지 않았습니다.", status=502)
            for part in item["content"]:
                if part.get("type") == "refusal":
                    fail("llm_response_blocked", "OpenAI가 응답 제공을 제한했습니다.", "입력 자료와 서비스 정책을 확인하세요. 자동 재시도하지 않습니다.", status=502)
                if part.get("type") == "output_text":
                    texts.append(part["text"])
        result = json.loads("".join(texts))
        if not isinstance(result, dict):
            raise ValueError("Expected an object")
        return result
    except (ValueError, KeyError, TypeError, AttributeError):
        fail("invalid_llm_response", "OpenAI 응답 형식을 확인하지 못했습니다.", "결과는 반영하지 않았습니다. 실행 이력을 확인하세요.", status=502)
