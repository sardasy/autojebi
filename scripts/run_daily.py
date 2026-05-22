"""GitHub Actions 또는 수동 실행용 일일 수집 스크립트"""
import asyncio
import sys
import os

# Windows에서 asyncpg는 SelectorEventLoop 필요 (ProactorEventLoop 미지원)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.repository import init_db  # noqa: E402
from src.main import run_daily_collection  # noqa: E402


async def main():
    await init_db()
    await run_daily_collection()


if __name__ == "__main__":
    asyncio.run(main())
