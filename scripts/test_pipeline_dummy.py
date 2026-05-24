"""더미 입찰공고로 전체 파이프라인 검증 (API 수집 없이)"""
import asyncio
import sys
import os
from datetime import datetime

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collector.base import RawBid  # noqa: E402
from src.db.repository import init_db, AsyncSessionLocal, BidRepository, OrgPriorRepository  # noqa: E402
from src.filter.keyword_matcher import KeywordMatcher  # noqa: E402
from src.filter.embedding_scorer import EmbeddingScorer  # noqa: E402
from src.filter.relevance import combined_score  # noqa: E402
from src.llm.gateway import LLMGateway  # noqa: E402
from src.db.models import Bid  # noqa: E402
from src.config import settings  # noqa: E402

DUMMY_BIDS = [
    RawBid(
        source="dummy",
        source_id="DUMMY-2026-001",
        title="○○변전소 154kV 수배전반 교체공사",
        organization="한국전력공사",
        category="공사",
        estimated_price=850_000_000,
        deadline=datetime(2026, 6, 15, 18, 0),
        announcement_date=datetime(2026, 5, 22, 9, 0),
        location="한국전력공사 경기지역본부",
        raw_content=(
            "154kV 수배전반 노후 설비 교체 및 디지털 보호계전기 적용 공사. "
            "수변전설비 전반 교체, GIS 설비 설치 포함. "
            "입찰 방법: 일반경쟁입찰, 사전심사 없음."
        ),
        detail_url="https://www.g2b.go.kr/dummy/001",
    ),
    RawBid(
        source="dummy",
        source_id="DUMMY-2026-002",
        title="태양광 발전소 ESS 배터리 유지보수 용역",
        organization="한국전력공사",
        category="용역",
        estimated_price=120_000_000,
        deadline=datetime(2026, 6, 10, 17, 0),
        announcement_date=datetime(2026, 5, 22, 10, 0),
        location="한국전력공사 전력연구원",
        raw_content=(
            "태양광 발전소 연계 ESS 배터리팩 정기점검, BMS 소프트웨어 업그레이드, "
            "비상발전기 성능시험 및 전력계통 연계 시험 포함."
        ),
        detail_url="https://www.g2b.go.kr/dummy/002",
    ),
    RawBid(
        source="dummy",
        source_id="DUMMY-2026-003",
        title="시청 주차장 바닥 도색 공사",
        organization="강남구청",
        category="공사",
        estimated_price=15_000_000,
        deadline=datetime(2026, 6, 5, 17, 0),
        announcement_date=datetime(2026, 5, 22, 8, 0),
        location="서울 강남구",
        raw_content="주차장 바닥 에폭시 도색 및 주차선 도색 공사.",
        detail_url="https://www.g2b.go.kr/dummy/003",
    ),
]


async def main():
    print("=" * 60)
    print("더미 파이프라인 테스트 시작")
    print("=" * 60)

    print("\n[1/5] DB 초기화...")
    await init_db()
    print("  ✓ DB 초기화 완료")

    keyword_matcher = KeywordMatcher()
    embedding_scorer = EmbeddingScorer()
    llm_gateway = LLMGateway()

    saved: list[Bid] = []

    async with AsyncSessionLocal() as session:
        repo = BidRepository(session)

        for raw in DUMMY_BIDS:
            print(f"\n{'─'*50}")
            print(f"[공고] {raw.title}")
            print(f"  기관: {raw.organization} | 카테고리: {raw.category}")
            if raw.estimated_price:
                print(f"  예가: {raw.estimated_price:,}원")

            # 기존 항목 중복 체크 (재실행 시 skip)
            if await repo.exists(raw.source_id):
                print("  → 이미 저장된 항목, 건너뜀")
                continue

            print("\n[2/5] 키워드 필터링...")
            kw_score = keyword_matcher.score(raw.title, raw.raw_content, raw.organization)
            print(f"  키워드 점수: {kw_score:.3f}")

            print("[3/5] 임베딩 유사도 점수...")
            emb_score = await embedding_scorer.score(f"{raw.title} {raw.raw_content[:500]}")
            print(f"  임베딩 점수: {emb_score:.3f}")

            prior = await OrgPriorRepository(session).get(raw.organization) if raw.organization else None
            relevance = combined_score(kw_score, emb_score, prior)
            prior_note = f"  prior: n={prior.n_samples} p={prior.p_relevant:.3f}" if prior else ""
            print(f"  최종 관련도: {relevance:.3f} (임계값: {settings.relevance_threshold}){prior_note}")

            if relevance < settings.relevance_threshold:
                print("  → 관련도 미달, 필터링됨 ✓")
                continue

            print("[4/5] LLM 요약 생성...")
            summary_out = await llm_gateway.summarize_bid(f"{raw.title}\n{raw.raw_content}")
            if summary_out:
                print(f"  요약: {summary_out.summary[:100]}...")
                print(f"  스펙: {summary_out.specs.model_dump()}")
            else:
                print("  경고: LLM 요약 실패 (None 반환)")

            print("[5/5] DB 저장...")
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
            saved_bid = await repo.save(bid)
            saved.append(saved_bid)
            print(f"  ✓ 저장 완료 (DB ID: {saved_bid.id})")

    print(f"\n{'='*60}")
    print(f"결과: {len(DUMMY_BIDS)}건 입력 → {len(saved)}건 저장")

    if saved:
        print("\n[알림 발송 시뮬레이션]")
        from src.notifier.teams_webhook import send_teams_notification
        from src.notifier.email_sender import send_email_notification
        await send_teams_notification(saved)
        await send_email_notification(saved)

    print("\n파이프라인 테스트 완료 ✓")


if __name__ == "__main__":
    asyncio.run(main())
