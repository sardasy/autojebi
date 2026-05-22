import uuid
from datetime import datetime
from sqlalchemy import String, Text, BigInteger, Float, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(200), unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    estimated_price: Mapped[int | None] = mapped_column(BigInteger)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    announcement_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(200))
    raw_content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    specs_json: Mapped[dict | None] = mapped_column(JSON)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    notifications: Mapped[list["NotificationLog"]] = relationship(back_populates="bid")


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bid_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bids.id"))
    channel: Mapped[str] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(50), default="sent")

    bid: Mapped["Bid"] = relationship(back_populates="notifications")
