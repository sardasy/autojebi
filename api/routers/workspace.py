from __future__ import annotations

import copy
import hashlib
import io
import os
from datetime import UTC, datetime
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, update

from api.auth import verify_api_key
from api.db import require_engine
from api.db.tables import bid_pipeline
from api.models.notices import NoticeSearchRequest, NoticeSearchResponse, NoticeUpsertRequest
from api.routers.company_assets import router as company_assets_router
from api.routers.notice_forms import router as notice_forms_router
from api.routers.notices import search_notices_endpoint, upsert_notice
from api.routers.requirement_candidates import router as requirement_candidates_router
from api.routers.specifications import router as specifications_router
from api.services.uploads import build_metadata, save_stream
from api.workspace import service
from api.workspace.assets import AssetLink
from api.workspace.errors import WorkspaceError
from api.workspace.execution import hwp_preview, source_path, storage_root
from api.workspace.identity import router as identity_router
from api.workspace.models import (
    AdoptRequirements,
    CommercialRequest,
    DecisionRequest,
    DocumentDraft,
    DocumentReview,
    JobRecord,
    JobRequest,
    OutputPlanRequest,
    RecoveryRequest,
    ReferenceDraft,
    RequirementRequest,
    ReviewRequest,
    SectionReview,
    SourceLinkRequest,
    SourceNeedsRequest,
    TextRequest,
    VersionRequest,
    WorkspaceNoticeRequest,
    WorkspaceRecord,
    WritingPlanRequest,
)
from api.workspace.prerequisites import Prerequisites, check_prerequisites
from api.workspace.provenance import (
    commercial_valid,
    evidence_valid,
    section_valid,
    source_quote_valid,
)
from api.workspace.source_inventory import (
    source_inventory,
    source_inventory_issues,
    source_text_complete,
)
from api.workspace.tables import jobs, workspaces

router = APIRouter(prefix="/v2", tags=["workspace"], dependencies=[Depends(verify_api_key)])

router.include_router(company_assets_router)
router.include_router(notice_forms_router)

router.include_router(specifications_router)
router.include_router(identity_router)
router.include_router(requirement_candidates_router)


async def _workspace_error_handler(request: Request, exc: WorkspaceError):
    # Same response (status, {"detail": ...}, headers) as FastAPI's HTTPException handler.
    return await http_exception_handler(request, exc)


def install_error_handlers(app: FastAPI) -> None:
    """Map v2 domain errors to HTTP responses. Call on every app that mounts ``router``."""
    app.add_exception_handler(WorkspaceError, _workspace_error_handler)


@router.post("/notices/{notice_no}/company-assets/{asset_id}", response_model=WorkspaceRecord)
def link_company_asset(notice_no: str, asset_id: str, body: AssetLink) -> WorkspaceRecord:
    from api.workspace.assets import link
    with require_engine().begin() as conn:
        link(conn, notice_no, asset_id, body)
        return service.view(conn, notice_no)


@router.get("/hwp-templates")
def workspace_templates():
    from api.routers.documents import list_hwp_templates
    return list_hwp_templates()


@router.get("/hwp-worker")
def workspace_hwp_worker():
    from api.services.hwp_agent_client import HwpAgentClient
    return HwpAgentClient(timeout_s=3, retries=1).diagnostics()


@router.get("/jobs/{job_id}/pages/{number}")
def job_page(job_id: str, number: int):
    from pathlib import Path
    job = get_job(job_id)
    pages = (job.result or {}).get("pages", [])
    if job.status != "succeeded" or not 1 <= number <= len(pages):
        service.fail("page_unavailable", "생성 페이지가 없습니다.", status=404)
    page = pages[number - 1]
    path = Path(page["path"])
    artifact = Path((job.result or {}).get("artifact", ""))
    if (path.is_symlink() or path.suffix != ".png" or
        not path.resolve().is_relative_to(storage_root() / "exports") or
        path.parent != artifact.parent / "draft-pages" or not path.is_file() or
        hashlib.sha256(path.read_bytes()).hexdigest() != page["sha256"]):
        service.fail("page_changed", "생성 페이지 파일을 확인할 수 없습니다.", status=409)
    return FileResponse(path, media_type="image/png")


@router.post("/search", response_model=NoticeSearchResponse)
def search(body: NoticeSearchRequest) -> NoticeSearchResponse:
    return search_notices_endpoint(body)


@router.get("/notices")
def list_workspaces(q: str = Query("", max_length=200), page: int = Query(1, ge=1)) -> dict:
    with require_engine().begin() as conn:
        query = select(bid_pipeline.c.notice_no, bid_pipeline.c.title).order_by(
            bid_pipeline.c.updated_at.desc()
        )
        if q:
            query = query.where(
                bid_pipeline.c.title.contains(q, autoescape=True)
                | bid_pipeline.c.notice_no.contains(q, autoescape=True)
            )
        rows = conn.execute(query.offset((page - 1) * 20).limit(21)).mappings().all()
        output = []
        for row in rows[:20]:
            exists = conn.execute(
                select(workspaces.c.notice_no).where(workspaces.c.notice_no == row["notice_no"])
            ).first()
            ws = service.view(conn, row["notice_no"]) if exists else None
            output.append({**row, "workspace": ws.model_dump(mode="json") if ws else None})
        return {"items": output, "page": page, "has_more": len(rows) > 20}


@router.post("/notices")
def register_notice(body: WorkspaceNoticeRequest) -> dict:
    if not body.notice_no.strip():
        service.fail("notice_required", "공고번호를 입력하세요.", status=422)
    with require_engine().connect() as conn:
        if conn.execute(
            select(bid_pipeline.c.notice_no).where(bid_pipeline.c.notice_no == body.notice_no)
        ).first():
            return {"notice_no": body.notice_no, "already_exists": True}
    raw = dict(body.raw or {})
    if body.org_name is not None:
        raw["ntceInsttNm"] = body.org_name
    if body.close_date is not None:
        raw["bidClseDt"] = body.close_date.isoformat()
    row = upsert_notice(NoticeUpsertRequest(notice_no=body.notice_no, title=body.title,
                                          source=body.source, raw=raw))
    return {"notice_no": row.notice_no}


@router.post("/notices/{notice_no}/initialize", response_model=WorkspaceRecord)
def initialize_workspace(notice_no: str) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        # Lock the existing notice so simultaneous initialization stays idempotent.
        conn.execute(
            select(bid_pipeline.c.notice_no)
            .where(bid_pipeline.c.notice_no == notice_no)
            .with_for_update()
        )
        service.initialize(conn, notice_no)
        return service.view(conn, notice_no)


@router.get("/notices/{notice_no}/workspace", response_model=WorkspaceRecord)
def get_workspace(notice_no: str) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        return service.view(conn, notice_no)


@router.put("/notices/{notice_no}/source-needs", response_model=WorkspaceRecord)
def update_source_needs(notice_no: str, body: SourceNeedsRequest) -> WorkspaceRecord:
    from api.workspace.source_needs import update as update_needs
    with require_engine().begin() as conn:
        update_needs(conn, notice_no, body)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/sync", response_model=WorkspaceRecord)
def sync_workspace(notice_no: str, body: VersionRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        service.initialize(conn, notice_no, body.version)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/decision", response_model=WorkspaceRecord)
def decide(notice_no: str, body: DecisionRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.change(conn, ws, ws["inputs"], "decision", body.note, decision=body.decision)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/jobs", response_model=JobRecord, status_code=202)
def create_job(notice_no: str, body: JobRequest) -> JobRecord:
    rejected = None
    with require_engine().begin() as conn:
        try:
            return JobRecord(**service.enqueue(conn, notice_no, body))
        except (HTTPException, WorkspaceError) as exc:
            if (
                body.kind not in {"hwp", "hwp_inspect"}
                or not conn.execute(
                    select(workspaces.c.notice_no).where(workspaces.c.notice_no == notice_no)
                ).first()
            ):
                raise
            ws = service.load(conn, notice_no)
            attempted = service.create_job_record(
                conn,
                ws,
                body.kind,
                "blocked:" + service.uid(),
                {
                    "template_key": body.template_key,
                    "attempt_only": True,
                    "requested_input_version": body.input_version,
                    "request_key_hash": service.digest(body.idempotency_key),
                },
            )
            detail = {**exc.detail, "job_id": attempted["id"]}
            conn.execute(
                update(jobs)
                .where(jobs.c.id == attempted["id"])
                .values(status="blocked", error=detail, finished_at=service.now())
            )
            rejected = HTTPException(status_code=exc.status_code, detail=detail)
    # Commit the blocked attempt before returning the rejected request to the caller.
    raise rejected


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str) -> JobRecord:
    with require_engine().connect() as conn:
        row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
        if not row:
            service.fail("job_not_found", "작업 기록이 없습니다.", status=404)
        return JobRecord(**row)


@router.post("/notices/{notice_no}/jobs/{job_id}/adopt-requirements", response_model=WorkspaceRecord)
def adopt_requirements(notice_no: str, job_id: str, body: AdoptRequirements) -> WorkspaceRecord:
    from api.workspace.quote_recovery import adopt
    with require_engine().begin() as conn:
        adopt(conn, notice_no, job_id, body)
        return service.view(conn, notice_no)


@router.get("/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    import mimetypes
    from pathlib import Path

    from api.services.exporters import HWP_MIME

    job = get_job(job_id)
    result = job.result or {}
    if job.status != "succeeded" or not result.get("artifact"):
        service.fail("artifact_unavailable", "완료된 생성 파일이 없습니다.", status=404)
    path = Path(result["artifact"]).resolve()
    if not path.is_relative_to(storage_root() / "exports") or not path.is_file():
        service.fail("artifact_missing", "생성 파일을 찾을 수 없습니다.", status=410)
    try:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        service.fail("artifact_unreadable", "생성 파일을 읽을 수 없습니다.",
                     "한글에서 해당 문서를 닫고 파일 접근 권한을 확인한 뒤 다시 다운로드하세요.", status=409)
    if checksum != result.get("sha256"):
        service.fail("artifact_changed", "생성 파일이 변경되었습니다.")
    media_type = HWP_MIME if path.suffix.lower() == ".hwp" else (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if path.suffix.lower() == ".xlsx" else
        mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    )
    return FileResponse(path, filename=f"{job.notice_no}-{job.input_version}-{path.name}",
                        media_type=media_type)


@router.post("/jobs/{job_id}/recover", response_model=JobRecord, status_code=202)
def recover_job(job_id: str, body: RecoveryRequest) -> JobRecord:
    with require_engine().begin() as conn:
        return JobRecord(**service.recover_job(conn, job_id, body))


@router.post("/notices/{notice_no}/jobs/{job_id}/apply", response_model=WorkspaceRecord)
def apply_job(notice_no: str, job_id: str, body: VersionRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.assert_source_current(conn, ws)
        job = (
            conn.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.notice_no == notice_no))
            .mappings()
            .first()
        )
        if not job or job["status"] != "succeeded" or job["input_version"] != ws["version"]:
            service.fail("stale_result", "현재 버전에서 완료된 결과만 반영할 수 있습니다.")
        inputs = copy.deepcopy(ws["inputs"])
        if job["kind"] == "fetch":
            existing = {d["id"]: d for d in inputs["documents"]}
            for document in job["result"]["documents"]:
                target = existing.get(document["id"])
                if target is None:
                    target = copy.deepcopy(document)
                    inputs["documents"].append(target)
                    existing[target["id"]] = target
                elif "attachment_index" in document and "attachment_url" in document:
                    if target.get("role") != "notice_source" or document.get("role") != "notice_source":
                        service.fail("source_identity_conflict", "회사·제품 증빙을 공고 첨부로 덮어쓸 수 없습니다.")
                    target.update(
                        attachment_index=document["attachment_index"],
                        attachment_url=document["attachment_url"],
                    )
        elif job["kind"] == "extract":
            for doc in inputs["documents"]:
                found = next((d for d in job["result"]["documents"] if d["id"] == doc["id"]), None)
                if found:
                    if doc.get("text") != found["text"]:
                        doc["confirmed"] = False
                    doc.update(text=found["text"], text_origin=found["format"])
                    if "extraction" in found:
                        doc["extraction"] = copy.deepcopy(found["extraction"])
                        if not found["extraction"].get("complete", False):
                            doc["confirmed"] = False
                            inputs["source_reviewed"] = False
        elif job["kind"] == "proposal":
            written = [s for s in inputs.get("proposal_sections") or [] if s.get("document_kind")]
            generated = job["result"]["sections"]
            if {s["id"] for s in written} & {s["id"] for s in generated}:
                service.fail("draft_conflict", "작성한 서류와 생성 결과의 식별자가 겹칩니다.")
            inputs["proposal_sections"] = written + generated
        elif job["kind"] == "analyze":

            def identity(requirement: dict) -> tuple:
                return tuple(
                    requirement.get(key) for key in ("document_id", "quote", "category", "text")
                )

            seen = {identity(r) for r in inputs["requirements"]}
            additions = []
            for requirement in job["result"]["requirements"]:
                key = identity(requirement)
                if key not in seen:
                    additions.append(
                        {**requirement, "id": service.uid(), "review_status": "pending",
                         "compliance": "unassessed"}
                    )
                    seen.add(key)
            if not additions:
                return service.view(conn, notice_no)
            inputs["requirements"].extend(additions)
        else:
            service.fail("not_applicable", "반영 대상 작업이 아닙니다.")
        if job["kind"] != "extract":
            inputs["source_reviewed"] = False
        if inputs == ws["inputs"]:
            return service.view(conn, notice_no)
        changed = service.change(
            conn,
            ws,
            inputs,
            "extract_result" if job["kind"] == "extract" else "apply_result",
            "사용자가 작업 결과를 검토 대상으로 반영",
        )
        if job["kind"] == "analyze":
            from api.specifications.service import sync_adopted
            sync_adopted(conn, changed)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/reference-drafts", response_model=WorkspaceRecord)
def reference_draft(notice_no: str, body: ReferenceDraft) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.assert_source_current(conn, ws)
        inputs = copy.deepcopy(ws["inputs"])
        requirement = next(
            (r for r in inputs.get("requirements", []) if r["id"] == body.requirement_id), None
        )
        document = next(
            (d for d in inputs.get("documents", []) if d["id"] == body.document_id), None
        )
        if not requirement or not document or document.get("role") != "company_reference":
            service.fail("reference_invalid", "이번 공고의 요구사항과 기존 작성자료를 선택하세요.", status=422)
        if not body.quote.strip() or body.quote not in (document.get("text") or ""):
            service.fail("reference_quote_invalid", "인용문이 기존 작성자료 본문과 일치하지 않습니다.", status=422)
        if not body.text.strip():
            service.fail("draft_empty", "이번 공고에 맞춘 작성 내용을 입력하세요.", status=422)
        inputs.setdefault("proposal_sections", []).append({
            "id": service.uid(), "text": body.text, "review_status": "pending",
            "requirement_ids": [requirement["id"]], "evidence_ids": [],
            "reference": {"document_id": document["id"], "name": document.get("name"),
                          "quote": body.quote, "input_version": ws["version"]},
        })
        service.change(conn, ws, inputs, "reference_draft", body.note)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/document-drafts", response_model=WorkspaceRecord)
def document_draft(notice_no: str, body: DocumentDraft) -> WorkspaceRecord:
    from api.workspace.document_drafts import save_draft

    with require_engine().begin() as conn:
        save_draft(conn, notice_no, body)
        return service.view(conn, notice_no)


@router.get("/notices/{notice_no}/document-drafts/{draft_id}/download")
def download_document_draft(notice_no: str, draft_id: str) -> Response:
    from api.workspace.document_drafts import draft_markdown

    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        section = next((s for s in ws["inputs"].get("proposal_sections", [])
                        if s["id"] == draft_id and s.get("document_kind")), None)
        if not section:
            service.fail("draft_missing", "작성한 서류가 없습니다.", status=404)
        return Response(draft_markdown(section), media_type="text/markdown",
                        headers={"Content-Disposition": 'attachment; filename="document-draft.md"'})


@router.put("/notices/{notice_no}/writing-plan", response_model=WorkspaceRecord)
def review_writing_plan(notice_no: str, body: WritingPlanRequest) -> WorkspaceRecord:
    from api.workspace.writing_plan import save

    with require_engine().begin() as conn:
        save(conn, notice_no, body)
        return service.view(conn, notice_no)


@router.put("/notices/{notice_no}/output-plan", response_model=WorkspaceRecord)
def review_output_plan(notice_no: str, body: OutputPlanRequest) -> WorkspaceRecord:
    from api.workspace.output_plan import save

    with require_engine().begin() as conn:
        save(conn, notice_no, body)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/sections/{section_id}/review", response_model=WorkspaceRecord)
def review_section(notice_no: str, section_id: str, body: SectionReview) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.assert_source_current(conn, ws)
        inputs = copy.deepcopy(ws["inputs"])
        section = next(
            (s for s in inputs.get("proposal_sections") or [] if s["id"] == section_id), None
        )
        if not section:
            service.fail("section_missing", "검토할 제안서 섹션이 없습니다.")
        section["text"] = body.text
        if body.requirement_ids is not None:
            section["requirement_ids"] = list(dict.fromkeys(body.requirement_ids))
        if body.evidence_ids is not None:
            section["evidence_ids"] = list(dict.fromkeys(body.evidence_ids))
        if body.approved and not section_valid(section, inputs):
            service.fail(
                "unverified_section", "미검증 내용이나 근거가 없는 섹션은 승인할 수 없습니다."
            )
        section.update(text=body.text, review_status="pending" if body.approved is None else "approved" if body.approved else "rejected")
        service.change(conn, ws, inputs, "section_review", body.note)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/documents", response_model=WorkspaceRecord)
def upload_document(
    notice_no: str,
    version: int = Form(...),
    role: Literal["notice_source", "company_evidence", "product_evidence", "company_reference"] = Form(...),
    file: UploadFile = File(...),
) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, version)
        saved = save_stream(
            file.file, notice_no=notice_no, original_name=file.filename or "upload.pdf"
        )
        doc = build_metadata(
            saved, original_name=file.filename or "upload.pdf", mime=file.content_type, item_id=None
        ).model_dump()
        doc.update(role=role, confirmed=False, text="", text_origin="unread")
        inputs = copy.deepcopy(ws["inputs"])
        inputs["documents"].append(doc)
        if role != "company_reference":
            inputs["source_reviewed"] = False
        service.change(conn, ws, inputs, "reference_upload" if role == "company_reference" else "upload", "원본 업로드; 준비완료로 자동 인정하지 않음")
        return service.view(conn, notice_no)


@router.get("/notices/{notice_no}/documents/{document_id}/download")
def download_source(notice_no: str, document_id: str, preview: bool = False) -> FileResponse:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        doc = next((d for d in ws["inputs"]["documents"] if d["id"] == document_id), None)
        if not doc:
            service.fail("document_missing", "문서를 찾을 수 없습니다.", status=404)
        path = source_path(doc)
        inline = preview and path.read_bytes()[:4] == b"%PDF"
        return FileResponse(path, filename=doc["name"], media_type="application/pdf" if inline else None,
                            content_disposition_type="inline" if inline else "attachment")


@router.post("/notices/{notice_no}/documents/{document_id}/source-link", response_model=WorkspaceRecord)
def link_source(notice_no: str, document_id: str, body: SourceLinkRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.assert_source_current(conn, ws)
        inputs = copy.deepcopy(ws["inputs"])
        doc = next((d for d in inputs["documents"] if d["id"] == document_id), None)
        if not doc:
            service.fail("document_missing", "연결할 문서가 없습니다.", status=404)
        if doc.get("role") != "notice_source":
            service.fail("notice_source_required", "공고 원문 문서만 공식 첨부에 연결할 수 있습니다.")
        attachment = next((a for a in source_inventory(inputs) if a["index"] == body.attachment_index), None)
        if not attachment:
            service.fail("attachment_missing", "현재 공고에 선언된 첨부 번호를 선택하세요.")
        doc.update(attachment_index=attachment["index"], attachment_url=attachment["url"])
        inputs["source_reviewed"] = False
        for requirement in inputs.get("requirements") or []:
            if document_id in {requirement.get("document_id"), requirement.get("evidence_id")}:
                requirement["compliance"] = "unassessed"
                if requirement.get("review_status") != "rejected":
                    requirement["review_status"] = "pending"
        service.change(conn, ws, inputs, "source_link", body.note)
        return service.view(conn, notice_no)


@router.get("/notices/{notice_no}/documents/{document_id}/preview")
def preview_source(notice_no: str, document_id: str, page: int = Query(1, ge=1, le=1000)) -> Response:
    import pdfplumber

    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        doc = next((d for d in ws["inputs"]["documents"] if d["id"] == document_id), None)
        if not doc:
            service.fail("document_missing", "문서를 찾을 수 없습니다.", status=404)
        path = source_path(doc)
    try:
        with pdfplumber.open(path) as pdf:
            if page > len(pdf.pages):
                service.fail("page_missing", "해당 페이지가 없습니다.", status=404)
            target = pdf.pages[page - 1]
            longest = max(target.width, target.height)
            if longest <= 0 or longest > 20000:
                service.fail("page_size", "미리보기에 적합하지 않은 페이지 크기입니다.", status=422)
            rendered = target.to_image(resolution=min(110, 1600 * 72 / longest))
            output = io.BytesIO()
            rendered.original.save(output, format="PNG")
            return Response(output.getvalue(), media_type="image/png", headers={"X-Page-Count": str(len(pdf.pages)), "Cache-Control": "no-store"})
    except (HTTPException, WorkspaceError):
        raise
    except Exception:
        service.fail("preview_unavailable", "PDF 미리보기를 만들 수 없습니다.", "추출 본문 또는 원본 다운로드로 확인하세요.", status=422)


@router.post("/notices/{notice_no}/documents/{document_id}/text", response_model=WorkspaceRecord)
def register_text(notice_no: str, document_id: str, body: TextRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        inputs = copy.deepcopy(ws["inputs"])
        doc = next((d for d in inputs["documents"] if d["id"] == document_id), None)
        if not doc:
            service.fail("document_missing", "문서를 찾을 수 없습니다.", status=404)
        doc.update(text=body.text, text_origin="manual_confirmed", confirmed=False)
        if doc.get("role") != "company_reference":
            inputs["source_reviewed"] = False
        service.change(conn, ws, inputs, "reference_text" if doc.get("role") == "company_reference" else "manual_text", body.note)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/documents/{document_id}/review", response_model=WorkspaceRecord)
def confirm_document(notice_no: str, document_id: str, body: DocumentReview) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        inputs = copy.deepcopy(ws["inputs"])
        doc = next((d for d in inputs["documents"] if d["id"] == document_id), None)
        if not doc:
            service.fail("document_missing", "문서를 찾을 수 없습니다.", status=404)
        if doc.get("role") == "company_reference":
            service.fail("reference_not_evidence", "기존 작성자료는 이번 공고의 증빙으로 승인할 수 없습니다.", status=422)
        if doc.get("role") == "notice_source" and body.role != "notice_source":
            service.fail(
                "source_not_evidence", "공고 원문은 회사·제품 증빙으로 인정할 수 없습니다."
            )
        if doc.get("company_asset") and body.role != doc.get("role"):
            service.fail("asset_role_immutable", "중앙 자료의 문서 구분은 변경할 수 없습니다.", status=422)
        if body.confirmed:
            from api.workspace.asset_policy import document_issue
            issue = document_issue(doc, inputs.get("company") or {})
            if issue:
                service.fail("asset_unverified", issue, "중앙 자료의 회사·유효기간을 확인하고 다시 연결하세요.")
            source_path(doc)
            if not doc.get("text"):
                service.fail("unread_document", "본문 확인 후 증빙을 확인하세요.")
        valid_items = {item["id"] for item in inputs["checklist"]}
        if body.checklist_id and body.checklist_id not in valid_items:
            service.fail("unknown_checklist", "필수 서류 목록의 항목을 선택하세요.")
        doc.update(
            role=body.role,
            confirmed=body.confirmed,
            item_id=body.checklist_id if body.role != "notice_source" else None,
        )
        service.change(conn, ws, inputs, "evidence_review", body.note)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/requirements", response_model=WorkspaceRecord)
def save_requirement(notice_no: str, body: RequirementRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.assert_source_current(conn, ws)
        inputs = copy.deepcopy(ws["inputs"])
        documents = {d["id"]: d for d in inputs["documents"]}
        requirement = body.model_dump(exclude={"version"})
        if not source_quote_valid(requirement, documents):
            service.fail("quote_mismatch", "인용문이 지정한 공고 원문에 없습니다.")
        if body.review_status == "accepted" and not evidence_valid(requirement, documents):
            service.fail("evidence_required", "확인된 증빙, 제안값, 근거 인용과 위치가 필요합니다.")
        if body.compliance != "unassessed" and body.review_status != "accepted":
            service.fail("compliance_requires_review", "원문·증빙 채택 후 충족 여부를 판정하세요.")
        if body.proposal_disposition == "evidence_only" and not body.proposal_note.strip():
            service.fail(
                "proposal_note_required",
                "제안서 본문 대신 증빙으로 충족할 사유를 입력하세요.",
                status=422,
            )
        if body.id and not any(r["id"] == body.id for r in inputs["requirements"]):
            service.fail("requirement_missing", "수정할 요구사항이 없습니다.")
        requirement["id"] = body.id or service.uid()
        inputs["requirements"] = [
            r for r in inputs["requirements"] if r["id"] != requirement["id"]
        ] + [requirement]
        inputs["source_reviewed"] = False
        changed = service.change(
            conn, ws, inputs, "requirement_review", "원문과 근거에 대한 담당자 입력 저장"
        )
        from api.specifications.service import sync_adopted
        sync_adopted(conn, changed)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/commercial", response_model=WorkspaceRecord)
def save_commercial(notice_no: str, body: CommercialRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.assert_source_current(conn, ws)
        inputs = copy.deepcopy(ws["inputs"])
        commercial = body.model_dump(exclude={"version"})
        documents = {d["id"]: d for d in inputs["documents"]}
        if not commercial_valid(commercial, documents):
            service.fail(
                "commercial_evidence_invalid",
                "확인된 회사·제품 증빙에서 원화 제안 총액과 정확한 인용·위치·검토 의견을 확인하세요.",
            )
        inputs["commercial"] = commercial
        service.change(conn, ws, inputs, "commercial_review", body.note)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/source-review", response_model=WorkspaceRecord)
def confirm_source(notice_no: str, body: TextRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, body.version)
        service.assert_source_current(conn, ws)
        inputs = copy.deepcopy(ws["inputs"])
        missing = source_inventory_issues(inputs)
        if missing:
            service.fail("source_incomplete", " / ".join(missing))
        if not source_text_complete(inputs) or not inputs["requirements"]:
            service.fail("source_incomplete", "모든 원문 본문과 요구사항 등록을 먼저 완료하세요.")
        inputs["source_reviewed"] = True
        service.change(conn, ws, inputs, "source_review", body.note)
        return service.view(conn, notice_no)


@router.post("/notices/{notice_no}/reviews", response_model=WorkspaceRecord)
def review_output(notice_no: str, body: ReviewRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        service.review_artifact(conn, notice_no, body)
        return service.view(conn, notice_no)


@router.get("/notices/{notice_no}/hwp-context")
def preview_hwp(notice_no: str, template_key: str = "bid_form") -> dict:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        value = hwp_preview(conn, ws["inputs"], template_key)
        return {
            "input_version": ws["version"],
            "template_key": template_key,
            "values": value["values"],
            "required_missing": value["required_missing"],
        }


@router.get("/notices/{notice_no}/prerequisites", response_model=Prerequisites)
def prerequisites(notice_no: str, template_key: str = Query("bid_form", max_length=100)) -> Prerequisites:
    with require_engine().connect() as conn:
        ws = service.load(conn, notice_no)
        _, signature = service.source_data(conn, notice_no)
        inspections = conn.execute(select(jobs.c.result, jobs.c.parameters).where(
            jobs.c.notice_no == notice_no, jobs.c.input_version == ws["version"],
            jobs.c.kind == "hwp_inspect", jobs.c.status == "succeeded",
        ).order_by(jobs.c.created_at.desc())).mappings()
        inspected = next((row["result"] for row in inspections
                          if row["parameters"].get("template_key") == template_key), None)
        return check_prerequisites(conn, ws["inputs"], ws["version"], template_key,
                                   source_changed=signature != ws["source_hash"], inspection=inspected)


@router.get("/settings")
def workspace_settings() -> dict:
    from api.config import settings
    from api.workspace.providers import configured_key, model_name

    with require_engine().connect() as conn:
        last = (
            conn.execute(
                select(jobs.c.kind, jobs.c.status, jobs.c.finished_at)
                .where(jobs.c.kind.in_(["analyze", "hwp"]), jobs.c.finished_at.is_not(None))
                .order_by(jobs.c.finished_at.desc())
                .limit(10)
            )
            .mappings()
            .all()
        )
    return {
        "configured": {
            "g2b": bool(settings.data_go_kr_api_key.strip()),
            "llm": bool(configured_key()),
            "hwp_token": bool(os.getenv("HWP_AGENT_TOKEN", "").strip()),
        },
        "llm": {
            "provider": settings.workspace_llm_provider,
            "model": model_name(),
            "key_registered": bool(configured_key()),
            "connection_status": "not_checked",
        },
        "last_checks": [dict(r) for r in last],
        "external_notifications": "dry_run_only",
        "worker": worker_health(),
    }


@router.get("/worker/health")
def worker_health() -> dict:
    from api.workspace.runtime_version import with_runtime_health

    return with_runtime_health(_worker_health_snapshot())


def _worker_health_snapshot() -> dict:
    from api.workspace.receipts import read_health

    lane_values = {}
    for lane in ("local", "external"):
        item = read_health(lane)
        if item:
            age = (datetime.now(UTC) - datetime.fromisoformat(item["heartbeat_at"].replace("Z", "+00:00"))).total_seconds()
            lane_values[lane] = {**item, "available": 0 <= age <= 20 and item["state"] != "stopped"}
    if any(item["available"] for item in lane_values.values()):
        value = lane_values.get("external") or lane_values["local"]
        return {**value, "lanes": lane_values,
                "available": len(lane_values) == 2 and all(item["available"] for item in lane_values.values())}
    value = read_health()
    if not value:
        return {"available": False, "state": "unknown", "heartbeat_at": None, "last_failure": None}
    stamp = datetime.fromisoformat(value["heartbeat_at"].replace("Z", "+00:00"))
    age = (datetime.now(UTC) - stamp).total_seconds()
    available = 0 <= age <= 20 and value["state"] != "stopped"
    return {**value, "available": available, "heartbeat_age_seconds": max(0, int(age))}
