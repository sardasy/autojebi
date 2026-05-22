import uuid
from datetime import datetime
from pydantic import BaseModel


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
    created_at: datetime

    model_config = {"from_attributes": True}
