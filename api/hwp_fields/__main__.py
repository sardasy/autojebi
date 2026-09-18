from __future__ import annotations

import argparse
import os
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from api.db import require_engine
from api.db.tables import company_profiles, document_field_mappings, hwp_templates
from api.services.hwp_fields import ALLOWED_TRANSFORMS

DEFAULT_TEMPLATES = [
    {
        "template_key": "bid_form",
        "kind": "bid_form",
        "name": "입찰참가신청서",
        "template_path": "templates/입찰참가신청서_양식.hwp",
        "template_version": "put_fields_v1",
    },
    {
        "template_key": "proposal",
        "kind": "proposal",
        "name": "제안서",
        "template_path": "templates/제안서_양식.hwp",
        "template_version": "put_fields_v1",
    },
]

DEFAULT_MAPPINGS = {
    "bid_form": [
        ("company_name", "company.company_name", True, None, "strip"),
        ("business_number", "company.business_number", True, None, "business_number_dash"),
        ("ceo_name", "company.ceo_name", True, None, "strip"),
        ("address", "company.address", True, None, "strip"),
        ("notice_no", "notice.notice_no", True, None, "strip"),
        ("title", "notice.title", True, None, "truncate_1000"),
        ("org_name", "notice.org_name", True, None, "strip"),
        ("base_price", "notice.base_price", False, None, "number_comma"),
        ("close_date", "notice.close_date", False, None, "date_yyyy_mm_dd"),
        ("spec_summary", "proposal.spec_summary", False, None, "truncate_1000"),
        (
            "technical_compliance_summary",
            "proposal.technical_compliance_summary",
            False,
            None,
            "truncate_1000",
        ),
    ],
    "proposal": [
        ("proposal_body", "proposal.body", True, None, "none"),
        ("company_name", "company.company_name", True, None, "strip"),
        ("business_number", "company.business_number", False, None, "business_number_dash"),
        ("notice_no", "notice.notice_no", True, None, "strip"),
        ("title", "notice.title", True, None, "truncate_1000"),
        ("org_name", "notice.org_name", True, None, "strip"),
        ("product_category", "proposal.values.product_category", False, None, "strip"),
        ("spec_summary", "proposal.values.spec_summary", True, None, "truncate_1000"),
        (
            "technical_compliance_summary",
            "proposal.values.technical_compliance_summary",
            True,
            None,
            "truncate_1000",
        ),
        ("top_sku_name", "proposal.values.top_sku_name", False, None, "strip"),
        ("close_date", "notice.close_date", False, None, "date_yyyy_mm_dd"),
        ("base_price", "notice.base_price", False, None, "number_comma"),
    ],
}


def seed(*, update_company_from_env: bool = False) -> None:
    engine = require_engine()
    with engine.begin() as conn:
        _upsert_company(conn, update_from_env=update_company_from_env)
        template_ids: dict[str, int] = {}
        for template in DEFAULT_TEMPLATES:
            row = _upsert_template(conn, template)
            template_ids[str(row["template_key"])] = int(row["id"])
        for template_key, rows in DEFAULT_MAPPINGS.items():
            template_id = template_ids[template_key]
            for sort_order, (field, path, required, default, transform) in enumerate(rows, start=10):
                if transform not in ALLOWED_TRANSFORMS:
                    raise ValueError(f"unsupported transform in seed: {transform}")
                _upsert_mapping(
                    conn,
                    {
                        "template_id": template_id,
                        "hwp_field_name": field,
                        "context_path": path,
                        "required": required,
                        "default_value": default,
                        "transform": transform,
                        "sort_order": sort_order,
                        "active": True,
                    },
                )


def _upsert_company(conn: Any, *, update_from_env: bool = False) -> None:
    values = {
        "profile_key": "default",
        "company_name": os.getenv("COMPANY_NAME", "").strip() or "미림씨스콘",
        "business_number": os.getenv("COMPANY_BUSINESS_NUMBER", "").strip(),
        "ceo_name": os.getenv("COMPANY_CEO_NAME", "").strip(),
        "address": os.getenv("COMPANY_ADDRESS", "").strip(),
        "profile_metadata": {},
        "active": True,
    }
    stmt = insert(company_profiles).values(**values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[company_profiles.c.profile_key],
    )
    conn.execute(stmt)
    if update_from_env:
        fields = {
            "company_name": "COMPANY_NAME", "business_number": "COMPANY_BUSINESS_NUMBER",
            "ceo_name": "COMPANY_CEO_NAME", "address": "COMPANY_ADDRESS",
        }
        changes = {field: os.getenv(env, "").strip() for field, env in fields.items() if os.getenv(env, "").strip()}
        if not changes:
            raise ValueError("No nonempty COMPANY_* settings to update")
        conn.execute(update(company_profiles).where(company_profiles.c.profile_key == "default").values(**changes))


def _upsert_template(conn: Any, values: dict[str, Any]) -> dict[str, Any]:
    stmt = insert(hwp_templates).values(**values, active=True)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[hwp_templates.c.template_key],
    )
    conn.execute(stmt)
    return dict(conn.execute(select(hwp_templates).where(hwp_templates.c.template_key == values["template_key"])).mappings().one())


def _upsert_mapping(conn: Any, values: dict[str, Any]) -> None:
    stmt = insert(document_field_mappings).values(**values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[document_field_mappings.c.template_id, document_field_mappings.c.hwp_field_name],
    )
    conn.execute(stmt)


def list_templates() -> list[dict[str, Any]]:
    engine = require_engine()
    with engine.begin() as conn:
        return [
            dict(row)
            for row in conn.execute(
                select(hwp_templates).order_by(hwp_templates.c.template_key)
            ).mappings()
        ]


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "list", "prepare-template"])
    parser.add_argument("--update-company-from-env", action="store_true", help="Explicitly update nonempty company settings; preserve metadata and activation")
    args = parser.parse_args()
    if args.command == "prepare-template":
        import json

        from api.hwp_fields.prepare import prepare_template

        print(json.dumps(prepare_template(), ensure_ascii=False))
    elif args.command == "seed":
        if args.update_company_from_env:
            seed(update_company_from_env=True)
        else:
            seed()
        print("added missing HWP defaults; existing templates and mappings preserved")
    else:
        if args.update_company_from_env:
            parser.error("--update-company-from-env requires seed")
        for row in list_templates():
            print(f"{row['template_key']}: {row['template_path']}")


if __name__ == "__main__":
    main()
