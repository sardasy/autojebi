from __future__ import annotations

import asyncio
import hmac
import os
import queue
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse

from api.hwp_worker.com_driver import ComDriverError
from api.hwp_worker.layout import Layout
from api.hwp_worker.paths import AllowedPaths, PathViolation
from api.hwp_worker.progress import Progress
from api.hwp_worker.queue import SerialQueue
from api.hwp_worker.recovery import RecoveryGuard, RecoveryRequired


class FileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=1024)
    visible: bool = False
    operation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,100}$")


class FieldsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    template_path: str = Field(min_length=1, max_length=1024)
    output_path: str = Field(min_length=1, max_length=1024)
    values: dict[str, str] = Field(min_length=1, max_length=2000)
    visible: bool = False
    render_pages: bool = False
    operation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,100}$")

    @field_validator("values")
    @classmethod
    def safe_fields(cls, values: dict[str, str]) -> dict[str, str]:
        for name, value in values.items():
            if (
                not name.strip()
                or len(name) > 200
                or any(char in name for char in ("\x00", "\x02", "{{", "}}"))
                or len(value) > 100_000
                or any(char in value for char in ("\x00", "\x02"))
            ):
                raise ValueError("invalid field name or value")
        if sum(len(value) for value in values.values()) > 1_000_000:
            raise ValueError("input values too large")
        return values


class TemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    base_template_path: str | None = Field(default=None, min_length=1, max_length=1024)
    output_path: str = Field(min_length=1, max_length=1024)
    layout: Layout
    visible: bool = False


def create_app(
    *,
    token: str | None = None,
    paths: AllowedPaths | None = None,
    driver: Any = None,
    timeout_s: float = 110,
) -> FastAPI:
    secret = (token if token is not None else os.getenv("HWP_AGENT_TOKEN", "")).strip()
    if len(secret) < 32:
        raise ValueError("HWP_AGENT_TOKEN must contain at least 32 characters")
    if paths is None:
        workspace = Path(os.getenv("WORKSPACE_DATA_DIR", "data/workspace"))
        paths = AllowedPaths(
            Path(os.getenv("HWP_TEMPLATE_ROOT", "data")),
            Path(os.getenv("HWP_SOURCE_ROOT", str(workspace / "uploads"))),
            Path(os.getenv("HWP_OUTPUT_ROOT", str(workspace / "exports"))),
        )
    if driver is None:
        from api.hwp_worker.com_driver import ComDriver

        driver = ComDriver()
    recovery = RecoveryGuard(paths.output_root)
    progress = Progress(paths.output_root)

    def com_call(operation):
        availability = driver.availability()
        if availability.get("available") is not True:
            raise ComDriverError(availability.get("code", "hwp_unavailable"), "availability")
        return recovery.run(operation)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.queue = SerialQueue()
        try:
            yield
        finally:
            app.state.queue.close()

    app = FastAPI(
        title="autoJEBI HWP Worker", lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )

    @app.middleware("http")
    async def authentication_first(request, call_next):
        supplied = request.headers.get("X-Agent-Token", "").encode("utf-8")
        if not hmac.compare_digest(secret.encode("utf-8"), supplied):
            return JSONResponse(status_code=401, content={"detail": {
                "code": "unauthorized", "message": "Worker 인증이 필요합니다.",
            }})
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > 4_000_000:
                return JSONResponse(status_code=413, content={"detail": {
                    "code": "request_too_large", "message": "필드 입력 요청 크기를 줄이세요.",
                }})
            chunks.append(chunk)
        # Starlette forwards this cached bounded body to the route after authentication.
        request._body = b"".join(chunks)
        return await call_next(request)

    async def invoke(operation, operation_id: str | None = None):
        if progress.uncertain or (not recovery.available() and not app.state.queue.state()["running"]):
            raise HTTPException(503, detail={"code": "recovery_required", "retry_safe": False,
                                            "message": "한글 작업 종료와 기존 파일 확인 후 복구하세요."})
        operation_id = operation_id or uuid4().hex
        def tracked():
            with progress.operation(operation_id):
                return operation()
        try:
            future = app.state.queue.submit(tracked)
        except (queue.Full, RuntimeError):
            raise HTTPException(503, detail={"code": "worker_busy", "message": "이전 한글 작업 완료 후 다시 확인하세요."}) from None
        try:
            wrapped = asyncio.wrap_future(future)
            wrapped.add_done_callback(lambda item: None if item.cancelled() else item.exception())
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout_s)
        except TimeoutError:
            cancelled = future.cancel()
            if not cancelled:
                progress.mark_failure()
                app.state.queue.close()
                recovery.mark_uncertain()
            raise HTTPException(504, detail={
                "code": "queue_timeout" if cancelled else "operation_uncertain",
                "message": "대기 작업이 취소되었습니다." if cancelled else "한글 응답 대기 중입니다. 기존 파일과 Worker를 확인한 후 복구하세요.",
                "retry_safe": cancelled,
                "operation_id": operation_id, "stage": progress.snapshot().get("stage"),
            }) from None
        except asyncio.CancelledError:
            if future.cancelled():
                raise HTTPException(503, detail={"code": "queue_cancelled", "retry_safe": True,
                                                "message": "이전 한글 작업 오류로 대기 요청이 취소되었습니다."}) from None
            raise
        except PathViolation as exc:
            raise HTTPException(422, detail={"code": str(exc), "message": "허용 폴더와 파일 경로를 확인하세요."}) from None
        except RecoveryRequired:
            raise HTTPException(503, detail={
                "code": "recovery_required", "retry_safe": False,
                "message": "이전 한글 작업의 종료 확인이 필요합니다. Worker를 중지하고 기존 한글 창·파일을 확인한 후 복구 승인하세요.",
            }) from None
        except ComDriverError as exc:
            phase = {
                "mutex": "이전 작업 확인", "initialize": "COM 초기화", "dispatch": "한글 실행",
                "visibility": "한글 창 설정", "open": "템플릿 열기", "enumerate": "필드 목록 조회",
                "write": "필드 입력", "save": "파일 저장", "reopen": "저장 파일 다시 열기",
                "readback": "저장값 재조회", "verify": "파일·입력값 대조", "close": "문서 닫기",
                "quit": "한글 종료", "cleanup": "한글 정리", "input": "입력 확인",
            }.get(exc.stage, "한글 연동")
            raise HTTPException(502, detail={
                "code": exc.code, "stage": exc.stage,
                "lifecycle": exc.lifecycle, "cleanup_errors": exc.cleanup_errors,
                "verification_detail": exc.verification_detail,
                "message": f"{phase} 단계에서 실패했습니다. 기존 파일과 한글 창을 확인하세요.",
                "retry_safe": False,
            }) from None
        except Exception:
            # COM exceptions may contain file contents, names and private filesystem paths.
            raise HTTPException(502, detail={"code": "hwp_operation_failed", "message": "한글 열기·필드 입력·저장·재조회에 실패했습니다. 한글 창과 기존 출력 파일을 확인하세요."}) from None

    @app.get("/health")
    def health():
        availability = driver.availability()
        queue_state = app.state.queue.state()
        recovery_required = progress.uncertain or (not recovery.available() and not queue_state["running"])
        return {
            "ok": availability.get("available") is True and not recovery_required,
            "component": "autojebi-hwp-worker", "contract_version": 1,
            "installation": availability, "queue": queue_state,
            "generation_verified": False,
            "recovery_required": recovery_required,
            "state": "recovery_required" if recovery_required else "running" if queue_state["running"] else "ready",
            "accepting": queue_state["accepting"] and not recovery_required,
            "operation": progress.snapshot(),
        }

    @app.post("/document/put-fields")
    async def put_fields(body: FieldsRequest):
        def operation():
            template = paths.resolve(body.template_path, "template")
            output = paths.resolve(body.output_path, "output")
            if template == output:
                raise PathViolation("template_overwrite")
            options = {"render_pages": True} if body.render_pages else {}
            return com_call(lambda: driver.put_fields(template, output, body.values, body.visible, **options))

        return await invoke(operation, body.operation_id)

    @app.post("/document/create-template")
    async def author_template(body: TemplateRequest):
        def operation():
            base = paths.resolve(body.base_template_path, "template") if body.base_template_path else None
            output = paths.resolve(body.output_path, "output")
            from api.hwp_worker.authoring import create_template
            return com_call(lambda: create_template(base, output, body.layout, body.visible))
        return await invoke(operation, body.operation_id)

    @app.post("/document/fields")
    async def fields(body: FileRequest):
        def operation():
            path = paths.resolve(body.path, "template")
            return com_call(lambda: driver.inspect(path, visible=True) if body.visible else driver.inspect(path))

        return await invoke(operation, body.operation_id)

    @app.post("/document/analyze-file")
    async def analyze(body: FileRequest):
        def operation():
            path = paths.resolve(body.path, "source")
            return com_call(lambda: driver.analyze(path))

        return await invoke(operation)

    return app
