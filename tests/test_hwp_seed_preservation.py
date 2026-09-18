import os
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.schema import CreateSchema

from api.hwp_fields import __main__ as seed_cli
from api.routers.notices import company_profiles, document_field_mappings, hwp_templates


def rows(engine):
    with engine.connect() as conn:
        return {
            table.name: [dict(row) for row in conn.execute(select(table).order_by(table.c.id)).mappings()]
            for table in (company_profiles, hwp_templates, document_field_mappings)
        }


@pytest.fixture
def seeded(sqlite_engine, monkeypatch):
    for name in ("COMPANY_NAME", "COMPANY_BUSINESS_NUMBER", "COMPANY_CEO_NAME", "COMPANY_ADDRESS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COMPANY_NAME", "Initial example")
    seed_cli.seed()
    return sqlite_engine


def test_repeat_seed_preserves_complete_rows(seeded):
    before = rows(seeded)
    seed_cli.seed()
    assert rows(seeded) == before
    assert len(before["company_profiles"]) == 1
    assert len(before["hwp_templates"]) == 2
    assert len(before["document_field_mappings"]) == 23


def test_seed_never_resets_operator_changes_or_reactivates_disabled_records(seeded, monkeypatch):
    with seeded.begin() as conn:
        conn.execute(update(company_profiles).values(company_name="Reviewed example", business_number="1234567890", ceo_name="Example", address="Reviewed address", profile_metadata={"reviewed": True}, active=False))
        conn.execute(update(hwp_templates).values(name="Reviewed template", template_path="templates/approved.hwpx", template_version="operator-v2", active=False))
        conn.execute(update(document_field_mappings).values(context_path="company.address", transform="strip", default_value="Reviewed default", required=True, sort_order=123, active=False))
    before = deepcopy(rows(seeded))
    monkeypatch.setenv("COMPANY_NAME", "Different environment value")
    seed_cli.seed()
    assert rows(seeded) == before


def test_explicit_company_update_only_changes_nonempty_fields(seeded, monkeypatch):
    with seeded.begin() as conn:
        conn.execute(update(company_profiles).values(business_number="1234567890", profile_metadata={"reviewed": True}, active=False))
    before = rows(seeded)
    monkeypatch.setenv("COMPANY_NAME", "Explicit example")
    monkeypatch.setenv("COMPANY_BUSINESS_NUMBER", " ")
    seed_cli.seed(update_company_from_env=True)
    after = rows(seeded)
    company = after["company_profiles"][0]
    assert company["company_name"] == "Explicit example"
    assert company["business_number"] == "1234567890"
    assert company["profile_metadata"] == {"reviewed": True}
    assert company["active"] is False
    assert after["hwp_templates"] == before["hwp_templates"]
    assert after["document_field_mappings"] == before["document_field_mappings"]


def test_empty_explicit_company_update_is_rejected_without_changes(seeded, monkeypatch):
    monkeypatch.delenv("COMPANY_NAME")
    before = rows(seeded)
    with pytest.raises(ValueError, match="No nonempty"):
        seed_cli.seed(update_company_from_env=True)
    assert rows(seeded) == before


def test_bad_new_default_rolls_back_all_insertions(sqlite_engine, monkeypatch):
    monkeypatch.setattr(seed_cli, "DEFAULT_MAPPINGS", {"bid_form": [("bad", "company.name", True, None, "eval")]})
    with pytest.raises(ValueError, match="unsupported transform"):
        seed_cli.seed()
    assert all(not value for value in rows(sqlite_engine).values())


@pytest.mark.skipif(not os.getenv("WORKSPACE_TEST_DATABASE_URL"), reason="isolated PostgreSQL is opt-in")
def test_postgres_seed_preserves_admin_edits(monkeypatch):
    engine = create_engine(os.environ["WORKSPACE_TEST_DATABASE_URL"])
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                schema = "seed_check_" + uuid4().hex
                conn.execute(CreateSchema(schema))
                conn = conn.execution_options(schema_translate_map={None: schema})
                for table in (company_profiles, hwp_templates, document_field_mappings):
                    table.create(conn)
                scoped = SimpleNamespace(begin=lambda: nullcontext(conn), connect=lambda: nullcontext(conn))
                monkeypatch.setattr(seed_cli, "require_engine", lambda: scoped)
                seed_cli.seed()
                conn.execute(update(company_profiles).values(profile_metadata={"manual_review": True}, active=False))
                conn.execute(update(hwp_templates).values(template_path="templates/confirmed.hwpx", active=False))
                conn.execute(update(document_field_mappings).values(context_path="company.address", active=False))
                before = rows(scoped)
                seed_cli.seed()
                assert rows(scoped) == before
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
