from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_go_kr_api_key: str = ""
    database_url: str = ""

    collect_hour: int = 8
    collect_minute: int = 0
    scheduler_enabled: bool = True

    bid_keywords: str = "ABB,차단기,변압기,인버터,전력변환,UPS,배전반,IGBT,모터드라이브"
    log_level: str = "INFO"

    # M2 — Claude analyzer
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    anthropic_max_tokens: int = 2048
    llm_attachment_fetch: bool = True
    g2b_attachment_dir: str = ""  # empty → tempfile.gettempdir()

    # M3 — RAG (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection_name: str = "abb_skus"

    # M3 — 3-axis grading
    grade_weight_spec: float = 0.5
    grade_weight_qual: float = 0.2
    grade_weight_price: float = 0.3
    grade_hard_gate_qual_zero: bool = True
    grade_alert_threshold: float = 0.6

    # M3 — Slack
    slack_webhook_url: str = ""

    # M3 — ABB 등록지역 (M5 자격 API 라이브 호출 시 region rule에 사용)
    abb_registered_regions: str = "서울,경기,전국"

    # M5 — 자동 grade 스케줄러
    scheduler_grade_enabled: bool = True
    grade_interval_minutes: int = 30
    grade_batch_limit: int = 50

    # M6 — 자격 API in-memory 캐시
    qual_cache_enabled: bool = True
    qual_cache_ttl_hours: int = 24

    # M7 — Next.js 프론트 CORS (CSV로 여러 origin 가능)
    frontend_origin: str = "http://localhost:3000"

    # M9 — API 키 인증 (빈값이면 비활성 — 개발 환경 친화)
    api_key: str = ""

    # M11 — 서류 자동화 v2: 사용자 업로드 + Excel/HWP 내보내기 저장소
    upload_dir: str = ""  # 빈값 → tempfile.gettempdir()/autojebi/uploads
    export_dir: str = ""  # 빈값 → tempfile.gettempdir()/autojebi/exports
    upload_max_bytes: int = 30_000_000  # 30MB
    upload_allowed_exts: str = "pdf,hwp,hwpx,jpg,jpeg,png,xlsx,docx"
    # 첨부 본문 기반 서류 판정용 — 파일당 보존할 추출 텍스트 길이(LLM/키워드 판정에 재사용)
    upload_text_excerpt_chars: int = 6000

    # E2E test helper endpoints. Keep disabled by default, especially in production.
    e2e_cleanup_enabled: bool = False

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip() for k in self.bid_keywords.split(",") if k.strip()]

    @property
    def grade_weights(self) -> dict[str, float]:
        return {
            "spec": self.grade_weight_spec,
            "qualification": self.grade_weight_qual,
            "price": self.grade_weight_price,
        }

    @property
    def abb_region_list(self) -> list[str]:
        return [r.strip() for r in self.abb_registered_regions.split(",") if r.strip()]

    @property
    def frontend_origins(self) -> list[str]:
        """CSV로 여러 origin 허용 가능 (예: 'http://localhost:3000,https://prod.example.com')."""
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]

    @property
    def auth_enabled(self) -> bool:
        """api_key가 설정되어 있을 때만 X-API-Key 검증 활성."""
        return bool(self.api_key.strip())

    @property
    def upload_allowed_ext_set(self) -> set[str]:
        """업로드 허용 확장자 집합 (소문자, 점 없음)."""
        return {
            ext.strip().lstrip(".").lower()
            for ext in self.upload_allowed_exts.split(",")
            if ext.strip()
        }

    def model_post_init(self, _context: Any) -> None:
        s = sum(self.grade_weights.values())
        if not 0.99 <= s <= 1.01:
            raise ValueError(f"grade_weight_* 합이 1.0이 아님: {s}")


settings = Settings()
