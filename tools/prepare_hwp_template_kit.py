"""Prepare real mapping-based authoring instructions and synthetic test inputs, not HWP files."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, select

from api.db.tables import document_field_mappings, hwp_templates
from api.workspace.hwp_inspection import mapping_hash


def main() -> None:
    load_dotenv(override=False)
    root = Path(os.environ["WORKSPACE_DATA_DIR"]).resolve(strict=True)
    folder = root / "template-kit" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        templates = (
            conn.execute(select(hwp_templates).where(hwp_templates.c.active.is_(True)))
            .mappings()
            .all()
        )
        for template in templates:
            mappings = [
                dict(row)
                for row in conn.execute(
                    select(document_field_mappings)
                    .where(
                        document_field_mappings.c.template_id == template["id"],
                        document_field_mappings.c.active.is_(True),
                    )
                    .order_by(document_field_mappings.c.sort_order)
                ).mappings()
            ]
            key = template["template_key"]
            if key not in {"bid_form", "proposal"}:
                continue
            values = {m["hwp_field_name"]: "시험용 값: " + m["hwp_field_name"] for m in mappings}
            if "proposal_body" in values:
                values["proposal_body"] = (
                    "시험용 긴 본문입니다. 실제 회사의 제안 내용이 아닙니다.\n" * 70
                )
            values["title"] = "시험용 한글 긴 공고명 · 줄바꿈과 페이지 배치 대조\n" * 10
            manifest = {
                "template_key": key,
                "template_path": template["template_path"],
                "mapping_sha256": mapping_hash(dict(template), mappings),
                "actual_hwp_created": False,
                "layout_review": "pending",
                "fields": [
                    {k: m[k] for k in ("hwp_field_name", "context_path", "required", "transform")}
                    for m in mappings
                ],
            }
            (folder / f"{key}-fields.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (folder / f"{key}-test-values.json").write_text(
                json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            rows = [
                f"# {template['name']} 제작 확인표",
                "",
                "상태: 제작 준비. 실제 HWP 파일 또는 제출용 서류가 아님.",
                "공고 지정 양식이 있으면 해당 양식을 우선 사용하고 원본의 복사본에 필드를 삽입한다.",
                "",
                "| 필드명 | 입력 원천 | 필수 | 변환 |",
                "|---|---|---|---|",
            ]
            rows += [
                f"| {m['hwp_field_name']} | {m['context_path']} | {'예' if m['required'] else '아니오'} | {m['transform']} |"
                for m in mappings
            ]
            rows += [
                "",
                "## 제작·검토 순서",
                "1. 회사·공고 식별 영역과 원문 지정 구성 확인.",
                "2. 위 필드명을 한글 누름틀에 동일하게 지정. 전체 본문은 페이지를 넘길 수 있는 본문 영역에 배치.",
                "3. 작업대 템플릿 필드 검사로 실제 목록과 중복 발생 번호 확인.",
                "4. 별도 시험값으로 생성 후 저장값·한글·표·페이지·본문 전체를 대조.",
                "5. 합성 시험값은 실제 공고의 증빙 또는 제안서 승인으로 승계하지 않음.",
            ]
            (folder / f"{key}-authoring.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(json.dumps({"kit_directory": str(folder), "actual_hwp_created": False}))


if __name__ == "__main__":
    main()
