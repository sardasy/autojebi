import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI
from src.config import settings
from src.db.repository import init_db, AsyncSessionLocal, BidRepository
from src.db.models import Bid
from src.collector.g2b_api import G2BCollector
from src.collector.kepco_api import KEPCOCollector
from src.collector.kpx_scraper import KPXScraper
from src.filter.keyword_matcher import KeywordMatcher
from src.filter.embedding_scorer import EmbeddingScorer
from src.llm.gateway import LLMGateway
from src.notifier.teams_webhook import send_teams_notification
from src.notifier.email_sender import send_email_notification
from src.collector.scheduler import setup_scheduler

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

keyword_matcher = KeywordMatcher()
embedding_scorer = EmbeddingScorer()
llm_gateway = LLMGateway()


async def run_daily_collection():
    logger.info("=== 일일 공고 수집 시작 ===")
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(hours=24)

    collectors = [G2BCollector(), KEPCOCollector(), KPXScraper()]
    all_raw = []
    for collector in collectors:
        try:
            bids = await collector.collect(date_from, date_to)
            all_raw.extend(bids)
        except Exception as e:
            logger.error(f"수집기 오류: {e}")

    logger.info(f"원시 수집: {len(all_raw)}건")

    saved: list[Bid] = []
    async with AsyncSessionLocal() as session:
        repo = BidRepository(session)
        for raw in all_raw:
            if not raw.source_id:
                continue
            if await repo.exists(raw.source_id):
                continue

            kw_score = keyword_matcher.score(raw.title, raw.raw_content, raw.organization)
            emb_score = await embedding_scorer.score(f"{raw.title} {raw.raw_content[:500]}")
            relevance = kw_score * 0.6 + emb_score * 0.4

            if relevance < settings.relevance_threshold:
                continue

            summary_out = await llm_gateway.summarize_bid(f"{raw.title}\n{raw.raw_content}")
            bid = Bid(
                source=raw.source,
                source_id=raw.source_id,
                title=raw.title,
                organization=raw.organization,
                category=raw.category,
                estimated_price=raw.estimated_price,
                deadline=raw.deadline,
                announcement_date=raw.announcement_date,
                location=raw.location,
                raw_content=raw.raw_content[:5000],
                summary=summary_out.summary if summary_out else None,
                specs_json=summary_out.specs.model_dump() if summary_out else None,
                relevance_score=relevance,
            )
            saved.append(await repo.save(bid))

    logger.info(f"관련 공고 저장: {len(saved)}건")

    if saved:
        top = sorted(saved, key=lambda b: b.relevance_score or 0, reverse=True)
        top = top[:settings.max_daily_notifications]
        await send_teams_notification(top)
        await send_email_notification(top)

    logger.info("=== 일일 공고 수집 완료 ===")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    sched = setup_scheduler(run_daily_collection)
    sched.start()
    logger.info(f"스케줄러 시작 (매일 {settings.collect_schedule_hour:02d}:{settings.collect_schedule_minute:02d} KST)")
    yield
    sched.shutdown()


app = FastAPI(title="AI 입찰 자동화 시스템 — 1단계", version="1.0.0", lifespan=lifespan)

from src.api.routes.bids import router as bids_router  # noqa: E402
app.include_router(bids_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
