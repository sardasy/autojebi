"""notices 라우터 패키지 — 구 api/routers/notices.py(단일 3천줄)를 도메인별로 분해.

서브모듈 라우터는 prefix/dependencies 없이 선언하고, 여기서 부모 라우터에
합쳐 prefix("/notices")와 인증 의존성을 일괄 부여한다.
"""

from fastapi import APIRouter, Depends

from api.auth import verify_api_key

# 하위 호환 re-export (기존 import 경로 유지: 테스트 20여 파일이 api.routers.notices에서 테이블을 import)
from api.tables import (  # noqa: F401
    attachment_fetch_files,
    attachment_fetch_jobs,
    bid_pipeline,
    company_profiles,
    document_field_mappings,
    hwp_generation_jobs,
    hwp_templates,
    metadata,
    notice_errors,
    notice_exports,
    notice_required_documents,
    notice_spec_items,
)

from . import (
    analysis,
    attachments,
    automation,
    crud,
    exports,
    hwp,
    intake,
    required_docs,
    spec_items,
    uploads,
)

# prefix는 include_router에 준다 — 구 파일의 APIRouter(prefix=...)와 동일한 최종 경로.
# (constructor prefix + 빈 경로("") 라우트는 include 시점에 FastAPIError가 나므로 여기서 부여)
router = APIRouter(
    tags=["notices"],
    dependencies=[Depends(verify_api_key)],
)

for _sub in (
    intake,
    analysis,
    spec_items,
    required_docs,
    automation,
    uploads,
    exports,
    hwp,
    attachments,
    crud,
):
    router.include_router(_sub.router, prefix="/notices")

# 분해 전 단일 파일의 데코레이터 등장 순서 = FastAPI 등록 순서 = 경로 매칭 순서.
# 서브모듈 include만으로는 원본의 교차 순서(예: crud의 upsert는 앞, summary/목록은 뒤)를
# 재현할 수 없어, include 후 원본 등록 순서로 재정렬한다.
# 리터럴 경로(/summary, /exports/by-id/...)가 파라미터 경로(/{notice_no}, {kind})보다
# 먼저 오는 원본 불변식이 그대로 유지된다.
_ORIGINAL_ROUTE_ORDER: dict[tuple[str, str], int] = {
    (path, method): index
    for index, (path, method) in enumerate(
        [
            ("/notices/extract-from-mail", "POST"),
            ("/notices/search", "POST"),
            ("/notices/upsert", "POST"),
            ("/notices/e2e/cleanup", "POST"),
            ("/notices/{notice_no}/analyze", "POST"),
            ("/notices/{notice_no}/notify", "POST"),
            ("/notices/{notice_no}/autofill-form", "POST"),
            ("/notices/{notice_no}/documents/analyze", "POST"),
            ("/notices/{notice_no}/spec-items/extract", "POST"),
            ("/notices/{notice_no}/spec-items", "GET"),
            ("/notices/{notice_no}/spec-items/{item_id}", "PATCH"),
            ("/notices/{notice_no}/required-documents/analyze", "POST"),
            ("/notices/{notice_no}/required-documents", "GET"),
            ("/notices/{notice_no}/required-documents/{doc_id}", "PATCH"),
            ("/notices/{notice_no}/documents/checklist/{item_id}", "PATCH"),
            ("/notices/{notice_no}/documents/validate", "POST"),
            ("/notices/{notice_no}/documents/hwp-context", "POST"),
            ("/notices/{notice_no}/documents/hwp-put-fields", "POST"),
            ("/notices/{notice_no}/documents/hwp-jobs/{job_id}/review", "POST"),
            ("/notices/{notice_no}/attachments/fetch", "POST"),
            ("/notices/{notice_no}/documents/uploads", "POST"),
            ("/notices/{notice_no}/documents/import-common/{upload_id}", "POST"),
            ("/notices/{notice_no}/documents/uploads", "GET"),
            ("/notices/{notice_no}/documents/uploads/{upload_id}", "DELETE"),
            ("/notices/{notice_no}/documents/uploads/{upload_id}/download", "GET"),
            ("/notices/{notice_no}/documents/exports/{kind}", "POST"),
            ("/notices/{notice_no}/documents/hwp-compose", "POST"),
            ("/notices/{notice_no}/documents/proposal-compose", "POST"),
            ("/notices/{notice_no}/documents/exports/by-id/{export_id}/download", "GET"),
            ("/notices/{notice_no}/documents/exports/{kind}/download", "GET"),
            ("/notices/{notice_no}/grade", "POST"),
            ("/notices/summary", "GET"),
            ("/notices/{notice_no}", "GET"),
            ("/notices", "GET"),
        ]
    )
}

def _route_order(route) -> int:
    key = (route.path, sorted(route.methods)[0])
    try:
        return _ORIGINAL_ROUTE_ORDER[key]
    except KeyError:
        raise RuntimeError(
            f"새 라우트 {key}가 _ORIGINAL_ROUTE_ORDER에 없습니다. "
            "리터럴 경로가 /{notice_no}보다 먼저 매칭되도록 순서를 정해 테이블에 추가하세요."
        ) from None


router.routes.sort(key=_route_order)
