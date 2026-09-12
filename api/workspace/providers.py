"""Provider selection without fallback; credentials never enter cached requests."""

from api.config import settings
from api.workspace import anthropic_client, gemini, openai_client


def configured_key() -> str:
    return {
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.google_api_key,
        "openai": settings.openai_api_key,
    }[settings.workspace_llm_provider].strip()


def model_name() -> str:
    return {
        "anthropic": settings.anthropic_model,
        "gemini": settings.gemini_model,
        "openai": settings.openai_model,
    }[settings.workspace_llm_provider].strip()


def prepare_request(request: dict) -> dict:
    if settings.workspace_llm_provider == "openai":
        return openai_client.prepare_request(request)
    return gemini.prepare_request(request)


def generate(request: dict) -> dict:
    """prepare_request 결과를 해당 공급자로 실행. provider 키가 없으면 Anthropic 원본 요청이다."""
    provider = request.get("provider", "anthropic")
    return {
        "anthropic": anthropic_client.generate,
        "gemini": gemini.generate,
        "openai": openai_client.generate,
    }[provider](request)
