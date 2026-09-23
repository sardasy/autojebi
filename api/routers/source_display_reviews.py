from fastapi import APIRouter

from api.db import require_engine
from api.workspace import service
from api.workspace.models import WorkspaceRecord
from api.workspace.source_display_reviews import SourceDisplayReview, save

router = APIRouter()


@router.post("/notices/{notice_no}/source-display-reviews", response_model=WorkspaceRecord)
def review_source_display(notice_no: str, body: SourceDisplayReview) -> WorkspaceRecord:
    with require_engine().begin() as conn:
        save(conn, notice_no, body)
        return service.view(conn, notice_no)
