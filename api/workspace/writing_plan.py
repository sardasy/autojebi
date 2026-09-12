"""Human-confirmed writing targets anchored to the current notice sources."""
import copy
import hashlib
import json
import re

from api.workspace.models import WritingPlanRequest


def source_signature(inputs: dict) -> str:
    sources = sorted(
        ({k: d.get(k) for k in ("id", "text", "sha256")} for d in inputs.get("documents", [])
         if d.get("role") == "notice_source"), key=lambda d: d["id"],
    )
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()


def current(inputs: dict) -> bool:
    plan = inputs.get("writing_plan") or {}
    return bool(plan.get("items") and plan.get("source_signature") == source_signature(inputs))


def save(conn, notice_no: str, body: WritingPlanRequest) -> None:
    from api.workspace import service

    ws = service.load(conn, notice_no, body.version)
    service.assert_source_current(conn, ws)
    inputs = copy.deepcopy(ws["inputs"])
    sources = {d["id"]: d for d in inputs.get("documents", []) if d.get("role") == "notice_source"}

    def normalize(value: str) -> str:
        return re.sub(r"\s+", "", value.replace("\x00", " "))

    ids: set[str] = set()
    names: set[str] = set()
    for item in body.items:
        doc = sources.get(item.document_id)
        quote, title = normalize(item.quote), normalize(item.title)
        if not doc or not quote or not title or quote not in normalize(doc.get("text") or "") or title not in quote:
            service.fail("writing_source_invalid", "항목명과 인용문을 실제 공고 원문에서 확인하세요.", status=422)
        if item.id in ids or title in names:
            service.fail("writing_duplicate", "같은 작성 항목을 중복 등록할 수 없습니다.", status=422)
        if item.action == "write" and re.search(r"사업자등록증|등기부등본|주민등록등본|인감증명서|신용등급확인서|중소기업\s*확인서|경쟁입찰참가자격등록증", item.title):
            service.fail("issued_document", "발급 증명서는 작성 대상이 아니라 원본 첨부 대상으로 지정하세요.", status=422)
        ids.add(item.id)
        names.add(title)
    items = [item.model_dump() for item in body.items]
    signature = source_signature(inputs)
    previous = inputs.get("writing_plan") or {}
    if previous.get("items") == items and previous.get("source_signature") == signature:
        return
    inputs["writing_plan"] = {"items": items, "source_signature": signature,
                              "reviewed_at": service.now().isoformat(), "reviewed_version": ws["version"], "note": body.note}
    inputs["checklist"] = [item for item in inputs.get("checklist", []) if not item.get("writing_target")]
    inputs["checklist"].extend({"id": item["id"], "name": item["title"], "writing_target": True}
                               for item in items if item["action"] == "attach")
    service.change(conn, ws, inputs, "writing_plan_review", body.note)
