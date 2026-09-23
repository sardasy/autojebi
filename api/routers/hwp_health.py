from fastapi import APIRouter

from api.services.hwp_health import diagnostics

router = APIRouter()


@router.get("/hwp-worker")
async def workspace_hwp_worker() -> dict:
    return await diagnostics()
