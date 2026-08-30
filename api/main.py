import logging
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

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
        return status

    return app


app = create_app()
