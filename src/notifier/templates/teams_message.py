from datetime import datetime
from src.db.models import Bid

_SCORE_EMOJI = [(0.9, "🔴"), (0.7, "🟡"), (0.0, "🟢")]


def _emoji(score: float) -> str:
    for threshold, emoji in _SCORE_EMOJI:
        if score >= threshold:
            return emoji
    return "🟢"


def build_teams_payload(bids: list[Bid], date: datetime) -> dict:
    date_str = date.strftime("%Y-%m-%d (%a) %H:%M")
    sections = []

    for bid in bids:
        score_pct = int((bid.relevance_score or 0) * 100)
        price_str = f"{bid.estimated_price // 100_000_000}억원" if bid.estimated_price else "미정"
        deadline_str = bid.deadline.strftime("%Y-%m-%d %H:%M") if bid.deadline else "미정"

        sections.append({
            "activityTitle": f"{_emoji(bid.relevance_score or 0)} [{score_pct}%] {bid.title}",
            "activityText": (
                f"**발주:** {bid.organization}<br>"
                f"**추정가:** {price_str}<br>"
                f"**마감:** {deadline_str}<br>"
                f"**요약:** {bid.summary or '(요약 없음)'}"
            ),
        })

    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": f"오늘의 맞춤 입찰공고 {len(bids)}건 — {date_str}",
        "themeColor": "0078D7",
        "title": f"📋 오늘의 맞춤 입찰공고 ({len(bids)}건) — {date_str}",
        "sections": sections,
    }
