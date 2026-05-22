import uuid
from datetime import datetime
from pydantic import BaseModel


class OrgCount(BaseModel):
    organization: str
    count: int


class DashboardStats(BaseModel):
    days: int
    total: int
    avg_relevance: float | None
    awarded: int
    new_count: int
    by_source: dict[str, int]
    by_category: dict[str, int]
    top_organizations: list[OrgCount]
    price_buckets: dict[str, int]


class TimeseriesPoint(BaseModel):
    date: str | None
    value: float


class AwardTrendPoint(BaseModel):
    month: str | None
    avg_award_ratio: float | None
    n: int


class BidResponse(BaseModel):
    id: uuid.UUID
    source: str
    title: str
    organization: str | None
    category: str | None
    estimated_price: int | None
    deadline: datetime | None
    relevance_score: float | None
    summary: str | None
    status: str
    award_status: str
    user_label: str | None
    detail_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
