from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class RawBid:
    source: str
    source_id: str
    title: str
    organization: str = ""
    category: str = ""
    estimated_price: int | None = None
    deadline: datetime | None = None
    announcement_date: datetime | None = None
    location: str = ""
    raw_content: str = ""
    detail_url: str = ""
    # PR 3: 첨부파일 (HWP/PDF) 파싱 결과 — 본문과 별도 보관
    attachment_text: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class RawAward:
    """낙찰 결과 1건. source_bid_id 가 Bid.source_id 와 매칭 키."""
    source: str
    source_award_id: str
    source_bid_id: str | None = None
    winner_name: str | None = None
    winner_biz_no: str | None = None
    award_price: int | None = None
    award_date: date | None = None
    participant_count: int | None = None
    raw: dict = field(default_factory=dict)


class BaseCollector(ABC):
    @abstractmethod
    async def collect(self, date_from: datetime, date_to: datetime) -> list[RawBid]:
        ...

    @abstractmethod
    async def get_detail(self, bid_id: str) -> str:
        ...
