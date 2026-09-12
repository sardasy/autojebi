"""Opt-in local UX harness. Real routes, in-memory DB, no external requests.

Run: python -m uvicorn workbench_mock_app:app --app-dir tests --port 8002
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, delete, update
from sqlalchemy.pool import StaticPool

import api.db
import api.ontology.tables  # noqa: F401
from api.collector.g2b_client import G2BClient, RawBid
from api.config import settings
from api.main import app  # noqa: F401
from api.routers import documents, notices
from api.services.hwp_agent_client import HwpAgentError, PutFieldsOutcome

settings.scheduler_enabled = False
settings.scheduler_grade_enabled = False
settings.api_key = ""
settings.anthropic_api_key = ""
settings.qdrant_url = ""
root = Path(tempfile.mkdtemp(prefix="autojebi-ux-mock-"))
settings.export_dir = str(root / "exports")
settings.upload_dir = str(root / "uploads")
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
notices.metadata.create_all(engine)
api.db.get_engine = lambda: engine


class Worker:
    base_url = "mock://hwp-worker"

    def health(self):
        return True

    def put_fields(self, **kwargs):
        values = kwargs["values"]
        mode = values.get("company_name", "")
        if mode == "FAIL":
            raise HwpAgentError("mock worker unavailable")
        path = root / f"mock-{datetime.now(UTC).timestamp()}.hwp"
        path.write_bytes(b"MOCK HWP - not a real Hangul document")
        return PutFieldsOutcome(
            str(path), list(values), [], ["address"] if mode == "WARNING" else [], {"mock": True}
        )


async def search(self, start, end, keyword):
    if keyword == "키없음":
        raise ValueError("G2B_KEY_MISSING")
    if keyword == "없음":
        return []
    return [
        RawBid(
            "UX-SEARCH",
            "00",
            "모의 검색 공고",
            "goods",
            "",
            "테스트 기관",
            "100000",
            None,
            None,
            None,
            {},
        )
    ]


G2BClient.search_single = search
notices._make_hwp_agent_client = Worker
documents.HwpAgentClient = Worker
now = datetime.now(UTC)


@app.post("/__test__/reset")
def reset_mock_jobs():
    with engine.begin() as conn:
        conn.execute(delete(notices.hwp_generation_jobs))
        conn.execute(delete(notices.notice_exports))
        conn.execute(
            delete(notices.bid_pipeline).where(notices.bid_pipeline.c.notice_no == "UX-SEARCH-00")
        )
        conn.execute(
            update(notices.notice_spec_items)
            .where(notices.notice_spec_items.c.notice_no == "UX-MOCK")
            .values(proposed_value="220V", status="matched")
        )
        conn.execute(
            update(notices.bid_pipeline)
            .where(notices.bid_pipeline.c.notice_no == "UX-MOCK")
            .values(
                analysis={
                    "document_automation": {
                        "checklist": [
                            {
                                "id": "business_registration",
                                "name": "사업자등록증",
                                "type": "company_common",
                                "required": True,
                                "status": "ready",
                                "source": "rule",
                            }
                        ],
                        "drafts": {},
                        "errors": [],
                        "uploads": [],
                        "exports": [],
                    }
                }
            )
        )
    return {"ok": True, "mock": True}


with engine.begin() as conn:
    conn.execute(
        notices.company_profiles.insert().values(
            profile_key="default", company_name="MOCK", profile_metadata={}, active=True
        )
    )
    template_id = conn.execute(
        notices.hwp_templates.insert().values(
            template_key="bid_form",
            name="모의 입찰양식",
            kind="bid_form",
            template_path="templates/mock.hwp",
            active=True,
        )
    ).inserted_primary_key[0]
    for field, context in [
        ("company_name", "company.company_name"),
        ("notice_no", "notice.notice_no"),
    ]:
        conn.execute(
            notices.document_field_mappings.insert().values(
                template_id=template_id,
                hwp_field_name=field,
                context_path=context,
                required=True,
                transform="none",
                active=True,
            )
        )
    conn.execute(
        notices.bid_pipeline.insert().values(
            notice_no="UX-MOCK",
            title="모의 공고 작업대 검증",
            source="test",
            raw={},
            category="ABB장비",
            fit_score=80,
            assignee="테스트",
            status="documents_analyzed",
            created_at=now,
            updated_at=now,
            graded_at=now,
            close_date=now + timedelta(days=7),
            analysis={
                "document_automation": {
                    "checklist": [
                        {
                            "id": "business_registration",
                            "name": "사업자등록증",
                            "type": "company_common",
                            "required": True,
                            "status": "ready",
                            "source": "rule",
                        }
                    ],
                    "drafts": {},
                    "errors": [],
                    "uploads": [],
                    "exports": [],
                }
            },
        )
    )
    for index, value in enumerate(["220V", ""]):
        conn.execute(
            notices.notice_spec_items.insert().values(
                notice_no="UX-MOCK",
                item_key=f"spec-{index}",
                label=f"전압 {index}",
                required_value=value,
                proposed_value="220V",
                category="technical",
                source="test",
                source_text="모의 규격서 220V",
                evidence={},
                status="matched",
                confidence=1,
            )
        )
