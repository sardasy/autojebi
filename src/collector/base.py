from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


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
    extra: dict = field(default_factory=dict)


class BaseCollector(ABC):
    @abstractmethod
    async def collect(self, date_from: datetime, date_to: datetime) -> list[RawBid]:
        ...

    @abstractmethod
    async def get_detail(self, bid_id: str) -> str:
        ...
