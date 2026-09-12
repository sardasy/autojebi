"""Original attachment form field discovery and review-copy export."""
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response

from api.db import require_engine
from api.workspace import notice_forms, service
from api.workspace.models import WorkspaceRecord
from api.workspace.notice_forms import FormFillingRequest

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


@router.get("/notices/{notice_no}/form-fillings/{document_id}/download")
def download_form_filling(notice_no: str, document_id: str) -> Response:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        service.assert_source_current(conn, ws)
        content, filename, report = notice_forms.export_filling(ws["inputs"], document_id)
    return Response(content, media_type="application/hwp+zip", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename),
        "X-Form-Review": "pending; layout-review-required; original-unchanged",
        "X-Form-SHA256": report["output_sha256"],
        "Cache-Control": "no-store",
    })
