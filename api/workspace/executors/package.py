"""Review package job: sources, approved outputs, filled forms and manifest (zip)."""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from api.workspace.document_drafts import draft_markdown, proposal_sections
from api.workspace.errors import fail
from api.workspace.forms.filling import export_filling
from api.workspace.forms.targets import retired
from api.workspace.output_plan import (
    LAYOUT_WARNING,
    review_matches,
    selected_artifacts,
    template_keys,
)
from api.workspace.readiness import readiness_issues
from api.workspace.readiness_issues import IssueCode, issue, render_blockers
from api.workspace.storage import artifact, source_path
from api.workspace.tables import jobs, reviews


def run_package(engine: Any, job: dict, folder: Path) -> dict:
    with engine.connect() as conn:
        artifacts = (
            conn.execute(
                select(jobs)
                .where(
                    jobs.c.notice_no == job["notice_no"],
                    jobs.c.input_version == job["input_version"],
                    jobs.c.kind.in_(["excel", "hwp"]),
                    jobs.c.status == "succeeded",
                )
                .order_by(jobs.c.created_at.desc(), jobs.c.id.desc())
            )
            .mappings()
            .all()
        )
        history = [
            dict(r)
            for r in conn.execute(
                select(reviews).where(reviews.c.notice_no == job["notice_no"])
            ).mappings()
        ]
    artifacts = selected_artifacts(artifacts, job["snapshot"])
    reasons = readiness_issues(job["snapshot"])
    for template_key in template_keys(job["snapshot"]):
        if not any(
            a["kind"] == "hwp" and a["parameters"].get("template_key") == template_key
            for a in artifacts
        ):
            reasons.append(issue(IssueCode.HWP_OUTPUT_MISSING, "artifact", template_key, template_key=template_key))
    if not any(a["kind"] == "excel" for a in artifacts):
        reasons.append(issue(IssueCode.EXCEL_OUTPUT_MISSING, "artifact", "excel"))
    manifest = {
        "notice_no": job["notice_no"],
        "input_version": job["input_version"],
        "readiness_checked_at": datetime.now(UTC).isoformat(),
        "inputs": copy.deepcopy(job["snapshot"]),
        "reviews": history,
        "files": [],
    }
    output = folder / "review-package.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for doc in job["snapshot"]["documents"]:
            path = source_path(doc)
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            if doc.get("sha256") and checksum != doc["sha256"]:
                fail("source_file_changed", "원본 파일 내용이 변경되었습니다.",
                     "새 버전으로 다시 등록하세요.")
            name = f"sources/{doc['id']}{path.suffix}"
            archive.writestr(name, content)
            manifest["files"].append(
                {"name": name, "sha256": checksum}
            )
        for item in artifacts:
            result = item["result"]
            path = Path(result["artifact"])
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            if checksum != result["sha256"]:
                fail("artifact_changed", "이전 생성물이 변경되어 패키지에 포함할 수 없습니다.")
            archive.writestr(f"outputs/{item['id']}{path.suffix}", content)
            latest_review = next(
                (
                    r
                    for r in sorted(history, key=lambda r: (r["created_at"], r["id"]), reverse=True)
                    if r["job_id"] == item["id"] and r["input_version"] == job["input_version"]
                ),
                None,
            )
            approved = review_matches(item, latest_review)
            if not approved:
                reasons.append(issue(IssueCode.ARTIFACT_REVIEW_REQUIRED, "artifact", item["id"], job_id=item["id"]))
            reasons.extend(issue(IssueCode.ARTIFACT_WARNING, "artifact", item["id"], message=w) for w in result.get("warnings") or []
                            if not (approved and item["kind"] == "hwp" and w == LAYOUT_WARNING))
            manifest["files"].append({"job_id": item["id"], "sha256": checksum})
        for filling in job["snapshot"].get("form_fillings") or []:
            if retired(job["snapshot"], filling):
                reasons.append(issue(IssueCode.FORM_RETIRED, "form", filling["document_id"]))
                continue
            content, filename, report = export_filling(job["snapshot"], filling["document_id"])
            name = f"forms/{hashlib.sha256(filling['document_id'].encode()).hexdigest()[:16]}.hwpx"
            archive.writestr(name, content)
            manifest["files"].append({"name": name, "title": filename,
                                      "sha256": hashlib.sha256(content).hexdigest(),
                                      "original_form": report})
            reasons.extend(issue(IssueCode.ARTIFACT_WARNING, "form", filling["document_id"], message=w)
                           for w in report.get("warnings") or [])
        # Keep source paths and historical snapshots out of the portable manifest.
        if "form_fillings" in manifest["inputs"]:
            manifest["inputs"]["form_fillings"] = [f for f in manifest["inputs"]["form_fillings"]
                                                      if not retired(job["snapshot"], f)]
        for doc in manifest["inputs"]["documents"]:
            doc.pop("storage_path", None)
        for review in history:
            review.pop("details", None)
        for section in job["snapshot"].get("proposal_sections") or []:
            if section.get("document_kind"):
                name = f"drafts/{hashlib.sha256(section['id'].encode()).hexdigest()[:16]}.md"
                content = draft_markdown(section).encode("utf-8")
                archive.writestr(name, content)
                manifest["files"].append({"name": name, "title": section["title"],
                                          "sha256": hashlib.sha256(content).hexdigest()})
        warnings = render_blockers(reasons, deduplicate=True)
        manifest["readiness_issues"] = [item.model_dump(mode="json") for item in reasons]
        manifest["warnings"] = warnings
        archive.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, default=str, indent=2)
        )
        archive.writestr("missing.txt", "\n".join(dict.fromkeys(warnings)))
        archive.writestr(
            "proposal.txt",
            "\n\n".join(s.get("text", "") for s in proposal_sections(job["snapshot"])),
        )
    return artifact(
        output, warnings, included_jobs=[item["id"] for item in artifacts],
        readiness_issues=manifest["readiness_issues"], readiness_input_version=job["input_version"],
        readiness_checked_at=manifest["readiness_checked_at"],
    )
