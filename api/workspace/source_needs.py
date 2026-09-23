"""Referenced document needs are recommendations until a person resolves them."""

import copy
import re
from typing import Any

from api.workspace import service
from api.workspace.quote_recovery import text_hash
from api.workspace.readiness_issues import IssueCode, ReadinessIssue, issue, render_blockers
from api.workspace.storage import source_path

LABELS = ("과업내용서", "과업지시서", "제안요청서", "평가표", "제출 서식")


def inventory(inputs: dict) -> list[dict]:
    saved = {item["id"]: item for item in inputs.get("source_needs", [])}
    docs = {d["id"]: d for d in inputs.get("documents", []) if d.get("role") == "notice_source"}
    result = []
    for label in LABELS:
        mentions = []
        for doc in docs.values():
            text = str(doc.get("text") or "")
            match = re.search(re.escape(label).replace(r"\ ", r"\s*"), text)
            if match:
                start, end = max(0, match.start() - 40), min(len(text), match.end() + 80)
                mentions.append({"document_id": doc["id"], "quote": text[start:end],
                                 "start": start, "source_text_sha256": text_hash(text)})
        if not mentions:
            continue
        identity = text_hash(label)[:16]
        old = saved.get(identity, {})
        signature = service.digest(mentions)
        valid = old.get("source_signature") == signature
        if old.get("state") in {"linked", "not_applicable"}:
            resolution = docs.get(old.get("document_id"), {})
            valid = valid and bool(resolution.get("text")) and old.get("resolution_text_sha256") == text_hash(resolution.get("text", ""))
        linked = docs.get(old.get("linked_document_id"), {})
        if old.get("state") == "linked":
            valid = valid and bool(linked.get("text")) and old.get("linked_text_sha256") == text_hash(linked.get("text", ""))
        result.append({"id": identity, "name": label, "mentions": mentions,
                       "source_signature": signature,
                       "state": old.get("state", "missing") if valid else "missing",
                       "linked_document_id": old.get("linked_document_id", "") if valid else "",
                       "note": old.get("note", ""), "resolution_quote": old.get("resolution_quote", "")})
    return result


def issues(inputs: dict) -> list[str]:
    return render_blockers(readiness_issues(inputs))


def readiness_issues(inputs: dict) -> list[ReadinessIssue]:
    return [issue(IssueCode.SOURCE_NEED_UNRESOLVED, "source_need", item["id"], name=item["name"])
            for item in inventory(inputs) if item["state"] == "missing"]


def update(conn: Any, notice_no: str, body: Any) -> None:
    ws = service.load(conn, notice_no, body.version)
    service.assert_source_current(conn, ws)
    inputs = copy.deepcopy(ws["inputs"])
    current = {item["id"]: item for item in inventory(inputs)}
    saved = {item["id"]: item for item in inputs.get("source_needs", [])}
    seen = set()
    for item in body.items:
        if item.id not in current or item.id in seen or not item.note.strip():
            service.fail("invalid_source_need", "문서 항목과 확인 의견을 다시 확인하세요.")
        seen.add(item.id)
        value = {**current[item.id], **item.model_dump()}
        if item.state != "missing":
            doc = next((d for d in inputs["documents"] if d["id"] == item.document_id
                        and d.get("role") == "notice_source"), None)
            if not doc or not item.resolution_quote.strip() or item.resolution_quote not in str(doc.get("text") or ""):
                service.fail("unverified_quote", "확인 근거가 공고 원문과 일치하지 않습니다.")
            source_path(doc)
            value["resolution_text_sha256"] = text_hash(doc["text"])
            if item.state == "linked":
                value["linked_document_id"] = doc["id"]
                value["linked_text_sha256"] = text_hash(doc["text"])
        saved[item.id] = value
    inputs["source_needs"] = list(saved.values())
    service.change(conn, ws, inputs, "source_needs", "참조 문서 확보·해당 여부 확인 저장")
