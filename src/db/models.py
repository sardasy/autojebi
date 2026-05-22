import uuid
from datetime import datetime, date
from sqlalchemy import (
    String, Text, BigInteger, Float, DateTime, Date, ForeignKey, JSON,
    Boolean, Integer, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    detail_url: Mapped[str | None] = mapped_column(String(500))
    raw_content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    specs_json: Mapped[dict | None] = mapped_column(JSON)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="new")
    award_status: Mapped[str] = mapped_column(String(30), default="open")
    user_label: Mapped[str | None] = mapped_column(String(20))
    user_label_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    notifications: Mapped[list["NotificationLog"]] = relationship(back_populates="bid")
    awards: Mapped[list["BidAward"]] = relationship(back_populates="bid")
    feedbacks: Mapped[list["BidFeedback"]] = relationship(back_populates="bid", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_bids_organization", "organization"),
        Index("ix_bids_category", "category"),
        Index("ix_bids_source_announcement_date", "source", "announcement_date"),
        Index("ix_bids_relevance_score", "relevance_score"),
    )


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bid_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bids.id"))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("alert_rules.id"))
    channel: Mapped[str] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(50), default="sent")

    bid: Mapped["Bid"] = relationship(back_populates="notifications")


class BidAward(Base):
    __tablename__ = "bid_awards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(50))
    source_award_id: Mapped[str] = mapped_column(String(200), unique=True)
    source_bid_id: Mapped[str | None] = mapped_column(String(200))
    winner_name: Mapped[str | None] = mapped_column(String(300))
    winner_biz_no: Mapped[str | None] = mapped_column(String(20))
    award_price: Mapped[int | None] = mapped_column(BigInteger)
    award_date: Mapped[date | None] = mapped_column(Date)
    participant_count: Mapped[int | None] = mapped_column(Integer)
    award_ratio: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    bid: Mapped["Bid | None"] = relationship(back_populates="awards")

    __table_args__ = (
        Index("ix_bid_awards_source_bid_id", "source_bid_id"),
        Index("ix_bid_awards_award_date", "award_date"),
    )


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_organizations: Mapped[list | None] = mapped_column(JSONB)
    filter_categories: Mapped[list | None] = mapped_column(JSONB)
    filter_sources: Mapped[list | None] = mapped_column(JSONB)
    filter_keywords: Mapped[list | None] = mapped_column(JSONB)
    min_price: Mapped[int | None] = mapped_column(BigInteger)
    max_price: Mapped[int | None] = mapped_column(BigInteger)
    min_relevance: Mapped[float] = mapped_column(Float, default=0.6)
    channels: Mapped[list | None] = mapped_column(JSONB)
    teams_webhook_url: Mapped[str | None] = mapped_column(String(500))
    email_recipients: Mapped[list | None] = mapped_column(JSONB)
    max_per_run: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class BidFeedback(Base):
    __tablename__ = "bid_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    bid: Mapped["Bid"] = relationship(back_populates="feedbacks")

    __table_args__ = (
        UniqueConstraint("bid_id", "reviewer", name="uq_bid_feedback_bid_reviewer"),
    )


class OrgPrior(Base):
    __tablename__ = "org_priors"

    organization: Mapped[str] = mapped_column(String(200), primary_key=True)
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    p_relevant: Mapped[float] = mapped_column(Float, default=0.5)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
