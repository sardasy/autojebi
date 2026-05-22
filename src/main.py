import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.config import settings
from src.db.repository import (
    init_db,
    AsyncSessionLocal,
    BidRepository,
    AlertRuleRepository,
    OrgPriorRepository,
)
from src.db.models import Bid
from src.collector.g2b_api import G2BCollector
from src.collector.kepco_api import KEPCOCollector
from src.collector.kpx_scraper import KPXScraper
from src.filter.keyword_matcher import KeywordMatcher
from src.filter.embedding_scorer import EmbeddingScorer
from src.filter.relevance import combined_score
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
        prior_repo = OrgPriorRepository(session)
        for raw in all_raw:
            if not raw.source_id:
                continue
            if await repo.exists(raw.source_id):
                continue

            kw_score = keyword_matcher.score(raw.title, raw.raw_content, raw.organization)
            emb_score = await embedding_scorer.score(f"{raw.title} {raw.raw_content[:500]}")
            prior = await prior_repo.get(raw.organization) if raw.organization else None
            relevance = combined_score(kw_score, emb_score, prior)

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
        async with AsyncSessionLocal() as session:
            rules = await AlertRuleRepository(session).list_enabled()
        for rule in rules:
            matched = [b for b in saved if rule.matches(b)]
            matched.sort(key=lambda b: b.relevance_score or 0, reverse=True)
            matched = matched[: rule.max_per_run]
            if not matched:
                continue
            channels = rule.channels or ["teams", "email"]
            if "teams" in channels:
                await send_teams_notification(
                    matched, webhook=rule.teams_webhook_url, rule_name=rule.name
                )
            if "email" in channels:
                await send_email_notification(
                    matched, recipients=rule.email_recipients, rule_name=rule.name
                )

    logger.info("=== 일일 공고 수집 완료 ===")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    sched = setup_scheduler(run_daily_collection)
    sched.start()
    logger.info(f"스케줄러 시작 (매일 {settings.collect_schedule_hour:02d}:{settings.collect_schedule_minute:02d} KST)")
    yield
    sched.shutdown()


app = FastAPI(title="AI 입찰 자동화 시스템 — 2단계", version="2.0.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

from src.api.routes.bids import router as bids_router  # noqa: E402
from src.api.routes.dashboard import router as dashboard_router  # noqa: E402
from src.api.routes.alert_rules import router as alert_rules_router  # noqa: E402
from src.api.routes.feedback import router as feedback_router  # noqa: E402
from src.api.routes.awards import router as awards_router  # noqa: E402
from src.api.routes.ui import router as ui_router  # noqa: E402

app.include_router(bids_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(alert_rules_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(awards_router, prefix="/api/v1")
app.include_router(ui_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
