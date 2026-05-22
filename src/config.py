from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Public APIs
    data_go_kr_api_key: str = Field(default="")
    kepco_api_key: str = Field(default="")

    # LLM
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")

    # Database
    database_url: str = Field(default="postgresql+asyncpg://bidding:bidding_pass@localhost:5432/bidding_db")
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Vector DB
    chroma_persist_dir: str = Field(default="./data/chroma")

    # Notification
    teams_webhook_url: str = Field(default="")
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    notification_recipients: str = Field(default="")

    # App
    relevance_threshold: float = Field(default=0.6)
    max_daily_notifications: int = Field(default=10)
    collect_schedule_hour: int = Field(default=8)
    collect_schedule_minute: int = Field(default=0)
    log_level: str = Field(default="INFO")

    @property
    def recipient_list(self) -> list[str]:
        return [r.strip() for r in self.notification_recipients.split(",") if r.strip()]

    # OCR
    clova_ocr_secret: str = Field(default="")
    clova_ocr_url: str = Field(default="")

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
