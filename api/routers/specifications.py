from fastapi import APIRouter, Header, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from api.db import require_engine
from api.specifications import service
from api.specifications.models import Correction, SearchRequest
from api.specifications.tables import specifications
from api.workspace import service as workspace

router = APIRouter(tags=["specifications"])


@router.get("/notices/{notice_no}/specifications")
def list_specifications(notice_no: str):
    with require_engine().begin() as conn:
        return service.listing(conn, workspace.load(conn, notice_no))


@router.get("/notices/{notice_no}/specifications/{spec_id}")
def get_specification(notice_no: str, spec_id: str, response: Response):
    service.require_enabled()
    with require_engine().begin() as conn:
        ws = workspace.load(conn, notice_no)
        row = conn.execute(select(specifications).where(specifications.c.id == spec_id,
                          specifications.c.notice_no == notice_no)).mappings().first()
        if not row:
            workspace.fail("spec_not_found", "사양이 없습니다.", status=404)
        value = service.public(row, ws, service.index_status(conn, ws))
        response.headers["ETag"] = value["etag"]
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(value)


@router.put("/notices/{notice_no}/specifications/{spec_id}")
def put_specification(notice_no: str, spec_id: str, body: Correction,
                      if_match: str | None = Header(None)):
    with require_engine().begin() as conn:
        return service.correct(conn, notice_no, spec_id, body, if_match)


@router.post("/notices/{notice_no}/spec-search")
def search_specifications(notice_no: str, body: SearchRequest):
    service.require_enabled()
    from api.specifications.indexing import search
    return search(require_engine(), notice_no, body)
