"""Category labels and role assignments have one authority and no approval side effect."""

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import get_args

import pytest
from sqlalchemy import select

from api.workspace.asset_catalog import AssetCategory, category_catalog, category_role
from api.workspace.tables import company_asset_events, company_assets, reviews, workspaces
from tests.test_company_assets import asset_env as _asset_env
from tests.test_company_assets import link, upload

asset_env = _asset_env


def test_catalog_covers_existing_types_and_is_content_addressed():
    catalog = category_catalog()
    assert {item.code for item in catalog.items} == set(get_args(AssetCategory))
    assert len(catalog.items) == len(get_args(AssetCategory))
    payload = [item.model_dump() for item in catalog.items]
    assert catalog.sha256 == hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                                     separators=(",", ":")).encode()).hexdigest()
    by_code = {item.code: item for item in catalog.items}
    assert by_code["sme_certificate"].label == "중소기업확인서"
    assert by_code["insurance_payment"].label == "4대보험 완납증명서"
    assert by_code["previous_proposal"].role == "company_reference"
    assert by_code["product_catalogue"].role == "product_evidence"
    assert category_role("unsupported-category") == "unknown"


def test_catalog_mutation_cannot_change_other_responses():
    first = category_catalog()
    first.items.clear()
    assert len(category_catalog().items) == 9
    with pytest.raises(ValueError):
        category_catalog().items[0].role = "company_reference"


def test_list_exposes_catalog_without_mutating_assets_or_notice_review(client, sqlite_engine, asset_env):
    asset = upload(client, category="previous_proposal")
    linked = link(client, asset).json()
    tables = (company_assets, company_asset_events, workspaces, reviews)
    with sqlite_engine.connect() as conn:
        before = [copy.deepcopy([dict(row) for row in conn.execute(select(table)).mappings()]) for table in tables]
    response = client.get("/v2/company-assets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["category_catalog"] == category_catalog().model_dump(mode="json")
    assert payload["items"][0]["role"] == "company_reference"
    assert not linked["inputs"]["documents"][0]["confirmed"] and not linked["ready"]
    with sqlite_engine.connect() as conn:
        after = [[dict(row) for row in conn.execute(select(table)).mappings()] for table in tables]
    assert after == before


def test_frontend_codes_match_and_does_not_define_its_own_category_labels():
    source = Path("frontend/src/lib/companyAssets.ts").read_text(encoding="utf-8")
    assert set(re.findall(r'^  \| "([a-z_]+)"', source, re.M)) == set(get_args(AssetCategory))
    component = Path("frontend/src/components/CompanyAssets.tsx").read_text(encoding="utf-8")
    for item in category_catalog().items:
        assert item.label not in component
