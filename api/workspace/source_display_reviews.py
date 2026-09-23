"""Human-only absence/equivalence records bound to immutable source identities."""

import copy
from typing import Literal

from pydantic import Field

from api.workspace import identity, notice_brief, service
from api.workspace.models import VersionRequest
from api.workspace.storage import source_path


class SourceDisplayReview(VersionRequest):
    kind: Literal["absent", "equivalent"]
    label: str = Field(default="", max_length=100)
    document_ids: list[str] = Field(min_length=1, max_length=100)
    source_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_checked: Literal[True]
    note: str = Field(min_length=1, max_length=2000)


def save(conn, notice_no: str, body: SourceDisplayReview) -> None:
    ws = service.load(conn, notice_no, body.version)
    service.assert_source_current(conn, ws)
    inputs = copy.deepcopy(ws["inputs"])
    documents = {d["id"]: d for d in notice_brief.sources(inputs)}
    selected = set(body.document_ids)
    if (len(selected) != len(body.document_ids) or not selected <= documents.keys()
            or not body.note.strip()
            or body.source_signature != notice_brief.digest(notice_brief.source_set(inputs))):
        service.fail("source_display_changed", "확인 대상 원본이 변경되었습니다. 다시 확인하세요.")
    if body.kind == "absent":
        if selected != documents.keys() or body.label not in notice_brief.LABELS:
            service.fail("absence_scope_incomplete", "전체 공고 원본과 확인 항목을 지정하세요.")
        brief = notice_brief.build(inputs)
        group = next(p for p in [brief["submission_state"], *brief["points"]] if p["label"] == body.label)
        if group["items"]:
            service.fail("absence_conflicts_with_source", "인용된 항목이 있습니다. 원문을 먼저 대조하세요.")
    elif len(selected) != 2:
        service.fail("equivalence_scope_invalid", "대조한 원본 두 개를 선택하세요.")
    scope = []
    for document_id in sorted(selected):
        doc = documents[document_id]
        if not doc.get("sha256"):
            service.fail("source_hash_missing", "원본 파일 해시를 먼저 확보하세요.")
        source_path(doc)
        scope.append({"id": document_id, "name": doc.get("name", ""), "sha256": doc["sha256"]})
    inputs.setdefault("source_display_reviews", []).append({
        **body.model_dump(exclude={"version", "document_ids"}), "scope": scope,
        "created_at": service.now().isoformat(), "actor": identity.audit_details({}).get("actor"),
    })
    service.change(conn, ws, inputs, "source_display_review", body.note)
