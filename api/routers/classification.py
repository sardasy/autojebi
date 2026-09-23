"""Read-only classification status; execution uses the existing writer-only jobs route."""

from fastapi import APIRouter

from api.db import require_engine
from api.workspace import classification, service

router = APIRouter()


@router.get("/notices/{notice_no}/classification", response_model=classification.ClassificationState)
def classification_state(notice_no: str) -> classification.ClassificationState:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no)
        _, signature = service.source_data(conn, notice_no)
        return classification.view(conn, ws, signature == ws["source_hash"])
