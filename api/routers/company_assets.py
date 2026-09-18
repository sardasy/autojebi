from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select

from api.db import require_engine
from api.workspace import assets
from api.workspace.asset_policy import validity
from api.workspace.storage import source_path
from api.workspace.tables import company_asset_events, company_assets

router = APIRouter(prefix="/company-assets")


@router.get("", response_model=assets.AssetList)
def list_assets(q: str = Query("", max_length=200), page: int = Query(1, ge=1),
                include_disabled: bool = False) -> assets.AssetList:
    with require_engine().connect() as conn:
        rows = conn.execute(select(company_assets).order_by(company_assets.c.updated_at.desc(),
                                                           company_assets.c.id)).mappings().all()
    alerts = {key:0 for key in ("expired", "expiring", "unknown", "not_yet_valid")}
    filtered = []
    for row in rows:
        state = validity(row["details"])
        if state in alerts:
            alerts[state] += 1
        if not include_disabled and not row["details"]["active"]:
            continue
        if q.strip().casefold() not in f"{row['details']['title']} {row['file']['name']}".casefold():
            continue
        filtered.append(row)
    start = (page - 1) * 20
    return assets.AssetList(items=[assets.public(dict(row)) for row in filtered[start:start+20]],
                            page=page, has_more=len(filtered)>start+20, alerts=alerts)


@router.post("", response_model=assets.AssetRecord, status_code=201)
def upload_asset(metadata: str = Form(...), file: UploadFile = File(...)) -> assets.AssetRecord:
    try:
        details = assets.AssetDetails.model_validate_json(metadata)
    except ValidationError:
        # Validation inputs can contain private company metadata; do not echo them.
        raise HTTPException(422, detail={"code":"asset_metadata_invalid", "message":"자료명·분류·사업자번호·유효기간을 확인하세요.",
                                        "next_action":"날짜 순서와 필수 항목을 확인하세요.", "job_id":None}) from None
    with require_engine().begin() as conn:
        return assets.public(assets.create(conn, file.file, file.filename or "", file.content_type, details))


@router.put("/{asset_id}", response_model=assets.AssetRecord)
def edit_asset(asset_id: str, body: assets.AssetEdit) -> assets.AssetRecord:
    with require_engine().begin() as conn:
        return assets.public(assets.edit(conn, asset_id, body))


@router.get("/{asset_id}/history")
def asset_history(asset_id: str) -> dict:
    with require_engine().begin() as conn:
        assets.load(conn, asset_id)
        rows = conn.execute(select(company_asset_events).where(company_asset_events.c.asset_id == asset_id)
                            .order_by(company_asset_events.c.version.desc())).mappings().all()
        return {"items":[dict(row) for row in rows]}


@router.get("/{asset_id}/download")
def download_asset(asset_id: str) -> FileResponse:
    with require_engine().begin() as conn:
        row = assets.load(conn, asset_id)
        path = source_path(row["file"])
        return FileResponse(path, filename=row["file"]["name"])
