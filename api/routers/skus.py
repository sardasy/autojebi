"""SKU 카탈로그 인제스트 라우터 (어드민용).

POST /skus/ingest — body.source (파일경로) 또는 body.skus (인라인 리스트) 중 하나 사용.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.auth import verify_api_key
from api.config import settings
from api.models.notices import IngestRequest, IngestResult
from api.sku.qdrant_store import QdrantStore
from api.sku.schemas import AbbSku

router = APIRouter(
    prefix="/skus",
    tags=["skus"],
    dependencies=[Depends(verify_api_key)],
)

_DEFAULT_CATALOG_PATH = "data/abb_catalog_sample.json"


@router.post("/ingest", response_model=IngestResult)
def ingest_skus(body: IngestRequest) -> IngestResult:
    if body.skus is not None and body.skus:
        try:
            skus = [AbbSku.model_validate(s) for s in body.skus]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"잘못된 SKU 페이로드: {exc}")
    else:
        path = Path(body.source or _DEFAULT_CATALOG_PATH)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"카탈로그 파일 없음: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            skus = [AbbSku.model_validate(item) for item in data]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"카탈로그 파싱 실패: {exc}")

    try:
        store = QdrantStore()
        n = store.ingest(skus)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Qdrant ingest 실패: {exc}")

    return IngestResult(ingested=n, collection=settings.qdrant_collection_name)
