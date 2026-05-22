from datetime import datetime
from src.db.models import Bid


def build_email_body(bids: list[Bid], date: datetime) -> str:
    date_str = date.strftime("%Y-%m-%d")
    lines = [f"<h2>오늘의 맞춤 입찰공고 ({len(bids)}건) — {date_str}</h2><hr>"]

    for i, bid in enumerate(bids, 1):
        score_pct = int((bid.relevance_score or 0) * 100)
        price_str = f"{bid.estimated_price // 100_000_000}억원" if bid.estimated_price else "미정"
        deadline_str = bid.deadline.strftime("%Y-%m-%d %H:%M") if bid.deadline else "미정"

        lines.append(f"""
<h3>{i}. [{score_pct}%] {bid.title}</h3>
<ul>
  <li>발주: {bid.organization}</li>
  <li>추정가: {price_str}</li>
  <li>마감: {deadline_str}</li>
  <li>요약: {bid.summary or '(요약 없음)'}</li>
</ul>
""")

    lines.append("<hr><p>상세 분석이 필요한 경우 회신해주세요.</p>")
    return "\n".join(lines)
