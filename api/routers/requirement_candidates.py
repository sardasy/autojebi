"""Read-only deterministic source hints under the workspace authentication dependency."""

from fastapi import APIRouter, Query

from api.db import require_engine
from api.workspace import service
from api.workspace.execution import source_path
from api.workspace.requirement_candidates import RequirementCandidatesResponse, find_candidates

router = APIRouter()


@router.get("/notices/{notice_no}/requirement-candidates", response_model=RequirementCandidatesResponse)
def requirement_candidates(notice_no: str, version: int | None = Query(None, ge=1)) -> RequirementCandidatesResponse:
    with require_engine().begin() as conn:
        ws = service.load(conn, notice_no, version)
        service.assert_source_current(conn, ws)
        for document in ws["inputs"].get("documents", []):
            if document.get("role") == "notice_source" and document.get("storage_path"):
                source_path(document)
        return find_candidates(ws["inputs"], ws["version"])
