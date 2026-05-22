import uuid
from datetime import datetime
from pydantic import BaseModel


class AlertRuleBase(BaseModel):
    name: str
    enabled: bool = True
    filter_organizations: list[str] | None = None
    filter_categories: list[str] | None = None
    filter_sources: list[str] | None = None
    filter_keywords: list[str] | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_relevance: float = 0.6
    channels: list[str] | None = None
    teams_webhook_url: str | None = None
    email_recipients: list[str] | None = None
    max_per_run: int = 10


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    filter_organizations: list[str] | None = None
    filter_categories: list[str] | None = None
    filter_sources: list[str] | None = None
    filter_keywords: list[str] | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_relevance: float | None = None
    channels: list[str] | None = None
    teams_webhook_url: str | None = None
    email_recipients: list[str] | None = None
    max_per_run: int | None = None


class AlertRuleResponse(AlertRuleBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeedbackCreate(BaseModel):
    bid_id: uuid.UUID
    label: str  # relevant|irrelevant|watch
    note: str | None = None
    reviewer: str | None = None


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    bid_id: uuid.UUID
    label: str
    note: str | None
    reviewer: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackStats(BaseModel):
    days: int
    counts: dict[str, int]
    recent: list[dict]


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
