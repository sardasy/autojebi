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

# 매칭 순서 불변식: 리터럴 경로가 같은 모양의 파라미터 경로보다 먼저 등록돼야 한다.
# 충돌 가능한 쌍은 둘뿐 — 둘 다 "같은 파일 내 선언 순서"로 보장된다:
#   (a) GET /summary, GET ""(목록)  vs  GET /{notice_no}  → crud.py에서 /{notice_no}를 마지막에 선언
#   (b) exports/by-id/{id}/download  vs  exports/{kind}/download → exports.py 선언 순서
# crud(캐치올 GET /{notice_no} 보유)를 마지막에 include해 다른 모듈의 리터럴 경로가 항상 앞선다.
# 주의: include 후 router.routes를 정렬/조작하지 말 것 — FastAPI 0.139+는 include_router가
# 라우트를 즉시 평탄화하지 않고 _IncludedRouter 플레이스홀더를 넣으므로 import 시점에 깨진다.
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

