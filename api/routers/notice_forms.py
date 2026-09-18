"""Original attachment form field discovery and review-copy export."""
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response

from api.db import require_engine
from api.workspace import service
from api.workspace.forms import filling as notice_forms
from api.workspace.forms.schemas import FormFillingRequest, FormReviewRequest, FormReviewTarget
from api.workspace.models import WorkspaceRecord

router = APIRouter()


@router.get("/notices/{notice_no}/form-fields")
def get_form_fields(notice_no: str) -> dict:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        service.assert_source_current(conn, ws)
        return notice_forms.inventory(ws)


@router.post("/notices/{notice_no}/form-fillings", response_model=WorkspaceRecord)
def save_form_filling(notice_no: str, body: FormFillingRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        notice_forms.save_filling(conn, notice_no, body)
        return service.view(conn, notice_no)


@router.get("/notices/{notice_no}/form-fillings/{document_id}/review", response_model=FormReviewTarget)
def get_form_review_target(notice_no: str, document_id: str) -> FormReviewTarget:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        service.assert_source_current(conn, ws)
        _, _, report = notice_forms.export_filling(ws["inputs"], document_id)
        return FormReviewTarget(version=ws["version"], **{
            key: report[key] for key in ("output_sha256", "unfilled_count", "review_status")})


@router.post("/notices/{notice_no}/form-fillings/{document_id}/review", response_model=WorkspaceRecord)
def review_form_filling(notice_no: str, document_id: str, body: FormReviewRequest) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        notice_forms.review_filling(conn, notice_no, document_id, body)
        return service.view(conn, notice_no)


@router.get("/notices/{notice_no}/form-fillings/{document_id}/download")
def download_form_filling(notice_no: str, document_id: str, version: int | None = None,
                          output_sha256: str | None = None) -> Response:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        service.assert_source_current(conn, ws)
        if version is not None and version != ws["version"]:
            service.fail("version_conflict", "입력이 변경되었습니다. 검토할 작성본을 다시 확인하세요.")
        content, filename, report = notice_forms.export_filling(ws["inputs"], document_id)
        if output_sha256 is not None and output_sha256 != report["output_sha256"]:
            service.fail("form_output_changed", "작성본이 변경되었습니다. 검토를 다시 시작하세요.")
    return Response(content, media_type="application/hwp+zip", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename),
        "X-Form-Review": ("approved; human-layout-reviewed; original-unchanged"
                          if report["review_status"] == "approved"
                          else "pending; layout-review-required; original-unchanged"),
        "X-Form-SHA256": report["output_sha256"],
        "Cache-Control": "no-store",
    })
