import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.collector.scheduler import start_scheduler, stop_scheduler
from api.config import settings
from api.db import MissingDatabaseUrl, get_engine
from api.routers.documents import router as documents_router
from api.routers.notices import router as notices_router
from api.routers.ontology import router as ontology_router
from api.routers.proposals import router as proposals_router
from api.routers.skus import router as skus_router
from api.routers.workspace import install_error_handlers as install_workspace_error_handlers
from api.routers.workspace import router as workspace_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def enforce_auth_policy() -> None:
    """운영 환경에서 X-API-Key 인증이 꺼진 채 기동되는 것을 막는다 (AGENTS.md §7).

    API_KEY 빈값은 개발 편의용 우회 모드다. APP_ENV=production 이면 기동 실패,
    그 외 환경이면 경고 로그만 남긴다.
    """
    if settings.auth_enabled:
        return
    if settings.app_env == "production":
        raise RuntimeError(
            "APP_ENV=production 에서는 API_KEY 가 필수입니다 (X-API-Key 인증 비활성 기동 금지)."
        )
    logging.getLogger(__name__).warning(
        "API_KEY 미설정 — X-API-Key 인증이 비활성 상태입니다 (APP_ENV=%s, 개발 전용).",
        settings.app_env,
    )


def create_app() -> FastAPI:
    # httpx INFO messages contain URLs, including G2B serviceKey query values.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    enforce_auth_policy()

    app = FastAPI(
        title="autojebi (Milim bid automation)",
        version="0.1.0",
        lifespan=lifespan,
    )

    # M7 — Next.js 프론트(:3000)가 API(:8001)를 호출할 때 CORS 허용
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(notices_router)
    app.include_router(documents_router)
    app.include_router(proposals_router)
    app.include_router(skus_router)
    app.include_router(ontology_router)
    app.include_router(workspace_router)
    install_workspace_error_handlers(app)

    @app.get("/healthz")
    def healthz() -> dict:
        """liveness/readiness probe.

        Always 200 OK — Docker HEALTHCHECK는 응답 본문의 `ok` 필드로 판단.
        DB 연결 실패해도 raise 안함 (장애 시점에 상태를 노출하기 위함).
        """
        status = {"ok": True, "checks": {}}
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            status["checks"]["db"] = "ok"
        except MissingDatabaseUrl:
            status["ok"] = False
            status["checks"]["db"] = "DATABASE_URL not set"
        except Exception as exc:  # noqa: BLE001
            status["ok"] = False
            status["checks"]["db"] = f"error: {str(exc)[:200]}"
        status["checks"]["DATA_GO_KR_API_KEY"] = (
            "ok" if settings.data_go_kr_api_key.strip() else "missing"
        )
        status["checks"]["ANTHROPIC_API_KEY"] = (
            "ok" if settings.anthropic_api_key.strip() else "missing"
        )
        status["checks"]["SLACK_WEBHOOK_URL"] = (
            "ok" if settings.slack_webhook_url.strip() else "missing"
        )
        status["checks"]["QDRANT_URL"] = "ok" if settings.qdrant_url.strip() else "missing"
        status["checks"]["HWP_AGENT_BASE_URL"] = (
            "ok" if os.getenv("HWP_AGENT_BASE_URL", "").strip() else "default"
        )
        status["checks"]["HWP_AGENT_TOKEN"] = (
            "ok" if os.getenv("HWP_AGENT_TOKEN", "").strip() else "missing"
        )
        return status

    return app


app = create_app()
