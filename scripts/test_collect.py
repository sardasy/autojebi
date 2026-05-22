"""DB 없이 API 수집 + 필터링 결과를 콘솔로 출력하는 테스트 스크립트"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collector.g2b_api import G2BCollector
from src.collector.kepco_api import KEPCOCollector
from src.filter.keyword_matcher import KeywordMatcher
from src.config import settings


async def main():
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(hours=24)

    print(f"\n{'='*60}")
    print(f"수집 기간: {date_from.strftime('%Y-%m-%d %H:%M')} ~ {date_to.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"관련도 임계값: {settings.relevance_threshold}")
    print(f"{'='*60}\n")

    matcher = KeywordMatcher()
    collectors = [("나라장터", G2BCollector()), ("한전", KEPCOCollector())]

    total_collected = 0
    matched = []

    for name, collector in collectors:
        print(f"[{name}] 수집 중...")
        try:
            bids = await collector.collect(date_from, date_to)
            total_collected += len(bids)
            print(f"[{name}] {len(bids)}건 수집")

            for bid in bids:
                score = matcher.score(bid.title, bid.raw_content, bid.organization)
                if score >= settings.relevance_threshold:
                    matched.append((score, bid))
        except Exception as e:
            print(f"[{name}] 오류: {e}")

    print(f"\n{'='*60}")
    print(f"총 수집: {total_collected}건  |  관련 공고 (score ≥ {settings.relevance_threshold}): {len(matched)}건")
    print(f"{'='*60}\n")

    if not matched:
        print("관련 공고 없음. 임계값을 낮추거나 기간을 늘려보세요.")
        return

    matched.sort(key=lambda x: x[0], reverse=True)
    for i, (score, bid) in enumerate(matched[:10], 1):
        price = f"{bid.estimated_price // 100_000_000}억원" if bid.estimated_price else "미정"
        deadline = bid.deadline.strftime("%Y-%m-%d") if bid.deadline else "미정"
        print(f"{i:2}. [{score:.0%}] {bid.title}")
        print(f"     발주: {bid.organization}  추정가: {price}  마감: {deadline}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
