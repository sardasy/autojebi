"""Source-only display facts. No classifications, approvals or LLM calls."""

import copy
import hashlib
import json
import re
import unicodedata

VERSION = 1
LABELS = ("제출서류", "제출 일정", "계약·수행 기간", "예산", "참가자격", "평가 기준", "제출 방법·유의사항")
BUDGET = r"(?:예산금액|사업예산|사업금액|총사업비|구축예산|추정가격|기초금액)"
PERIOD = r"(?:납품설치기한|납품기한|계약기간|과업기한|수행기간|용역기간)"
PATTERNS = (
    r"(?:제출서류[:：]|제출자료[:：]|(?:등록증|증명서|확인서|인감계|제안서).*\d+(?:부|식))",
    r"(?:제출.{0,15}(?:마감|개시|시작|기한)|제출기간).*(?:\d{4}[./년]|공고.*참조)",
    r"^(?:\d+(?:\.\d+)*[.)]?|[○◦•◇-])*" + PERIOD + r"[:：]?(?:계약|착수|\d|.*이내)",
    BUDGET + r"[:：]?(?:총)?(?:금)?\d[\d,]*(?:\.\d+)?(?:원|천원|백만원|억원)",
    r"(?:확인서를소지한자|업종.*등록한|참가자격제한을받지|입찰에참가할수없)",
    r"(?:평가방법[:：]|종합평가비율|(?:평가|종합평점).*\d+(?:\.\d+)?점이상.*(?:적격|선정|협상))",
    r"(?:제출방법[:：]|PDF.*(?:형식|용량|MB)|미제출.*무효|하나라도제출하지|주민등록번호.*비공개)",
)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sources(inputs: dict) -> list[dict]:
    return [d for d in inputs.get("documents", []) if d.get("role") == "notice_source"]


def source_set(inputs: dict) -> list[dict]:
    return sorted([{"id": d["id"], "sha256": d.get("sha256"),
                    "text_sha256": hashlib.sha256(d.get("text", "").encode()).hexdigest()}
                   for d in sources(inputs)], key=lambda d: d["id"])


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def presentation_free(inputs: dict) -> dict:
    """Strip ONLY new display/review metadata, not extraction completeness or failures."""
    value = copy.deepcopy(inputs)
    value.pop("source_display_reviews", None)

    def strip(meta: dict) -> None:
        meta.pop("presentation", None)
        for member in meta.get("members", []):
            strip(member.get("extraction", {}))

    for doc in value.get("documents", []):
        strip(doc.get("extraction", {}))
    return value


def extraction_issues(doc: dict) -> list[str]:
    issues = []

    def visit(meta: dict, where: str) -> None:
        if meta.get("complete") is False:
            issues.append(f"{where}: 본문 추출 불완전")
        layout = meta.get("presentation", {})
        if layout.get("status") == "partial":
            issues.extend(f"{where}: {code}" for code in layout.get("issues") or ["구조 일부 누락"])
        if meta.get("table_structure", {}).get("status") in {"partial", "needs_review"}:
            issues.append(f"{where}: 표 구조 확인 필요")
        for member in meta.get("members", []):
            location = f"{where} / {member['name']}"
            if member.get("complete") is False:
                issues.append(f"{location}: {member.get('error_code') or '내부 문서 추출 불완전'}")
            visit(member.get("extraction", {}), location)

    visit(doc.get("extraction", {}), doc.get("name", doc["id"]))
    return list(dict.fromkeys(issues))


def groups(inputs: dict) -> list[list[str]]:
    docs = sources(inputs)
    result: list[list[str]] = []
    for doc in docs:
        text = normalized(doc.get("text", ""))
        peer = next((d for d in docs if d["id"] != doc["id"] and text
                     and d.get("extraction", {}).get("complete") is True
                     and doc.get("extraction", {}).get("complete") is True
                     and not extraction_issues(d) and not extraction_issues(doc)
                     and normalized(d.get("text", "")) == text), None)
        linked = next((g for g in result if doc["id"] in g or (peer and peer["id"] in g)), None)
        if linked is not None:
            if doc["id"] not in linked:
                linked.append(doc["id"])
        else:
            result.append([doc["id"]])
    current = {d["id"]: d.get("sha256") for d in docs}
    for review in inputs.get("source_display_reviews", []):
        if review.get("kind") != "equivalent" or not all(
            current.get(d["id"]) == d["sha256"] for d in review["scope"]
        ):
            continue
        ids = {d["id"] for d in review["scope"]}
        merged = [g for g in result if ids.intersection(g)]
        result = [g for g in result if g not in merged] + [list(dict.fromkeys(i for g in merged for i in g))]
    return result


def chunks(doc: dict) -> tuple[list[dict], list[str]]:
    text = doc.get("text") or ""
    layout = doc.get("extraction", {}).get("presentation", {})
    spans, issues = [], []
    valid_hash = layout.get("text_sha256") == hashlib.sha256(text.encode()).hexdigest()
    for item in layout.get("spans", []):
        start, end = item.get("start"), item.get("end")
        if not valid_hash or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            issues.append("표시 구조와 본문 위치 불일치")
            continue
        spans.append(dict(item))
    if not spans:
        # No synthetic text: every fallback chunk is still an original substring.
        boundaries = [0, *[m.end() for m in re.finditer(
            r"\r?\n+|\s+(?=[①-⑳○◦•◇]|\d{1,2}[.)]\s+[가-힣「]|[가-하]\.\s)", text)], len(text)]
        spans = [{"start": a, "end": b, "locator": f"본문 {a}:{b}"}
                 for a, b in zip(boundaries, boundaries[1:], strict=False) if a < b]
    spans.sort(key=lambda s: (s["start"], s["end"]))
    # Join bare labels to the following paragraph/cell without discarding source whitespace.
    additions = []
    for index, span in enumerate(spans[:-1]):
        bare = re.sub(r"\s+", "", text[span["start"]:span["end"]]).strip(" :：○◦•-")
        if re.fullmatch(f"{BUDGET}|{PERIOD}|제안서제출기한", bare):
            additions.append({**span, "end": spans[index + 1]["end"]})
        following = spans[index + 1]
        if following["start"] >= span["end"] and re.match(
            r"\s*(?:단[,，\s]|다만|※|\(?허위|\(?서류가.*경우)", text[following["start"]:following["end"]]
        ):
            span["end"] = following["end"]
    return [*spans, *additions], issues


def build(inputs: dict) -> dict:
    documents = sources(inputs)
    aliases = groups(inputs)
    representatives = {group[0] for group in aliases}
    found: list[list[dict]] = [[] for _ in LABELS]
    warnings = []
    for doc in documents:
        warnings.extend(extraction_issues(doc))
        spans, issues = chunks(doc)
        warnings.extend(f"{doc.get('name', doc['id'])}: {i}" for i in issues)
        if doc["id"] not in representatives:
            continue
        text = doc.get("text") or ""
        for span in spans:
            quote = text[span["start"]:span["end"]]
            if not quote.strip() or len(quote) > 4000:
                continue
            compact = re.sub(r"\s+", "", quote)
            for index, pattern in enumerate(PATTERNS):
                if re.search(pattern, compact) and not any(
                    old["documentId"] == doc["id"] and quote.strip() == old["quote"].strip()
                    for old in found[index]
                ):
                    found[index].append({"text": normalized(quote), "quote": quote,
                        "documentId": doc["id"], "documentName": doc.get("name", ""),
                        "start": span["start"], "end": span["end"], "locator": span["locator"],
                        "source_sha256": doc.get("sha256"), "member_path": span.get("member_path", [])})
    signature = digest(source_set(inputs))
    points = []
    for index, label in enumerate(LABELS):
        absent = next((r for r in reversed(inputs.get("source_display_reviews", []))
                       if r.get("kind") == "absent" and r.get("label") == label
                       and r.get("source_signature") == signature), None)
        state = "found" if found[index] else "absent_confirmed" if absent else "incomplete" if warnings else "not_detected"
        points.append({"label": label, "items": found[index], "state": state,
                       "absence": absent if state == "absent_confirmed" else None})
    return {"version": VERSION, "signature": digest([[p["label"], p["items"]] for p in points]),
            "submissions": found[0], "points": points[1:], "submission_state": points[0],
            "warnings": list(dict.fromkeys(warnings)), "document_groups": aliases,
            "source_signature": signature}


def review_snapshot(inputs: dict) -> dict:
    brief = build(inputs)
    return {"version": brief["version"], "signature": brief["signature"]}


def audit_snapshot(action: str, inputs: dict, details: dict) -> dict:
    kinds = {"evidence_review": ("documents", "confirmed", True),
             "requirement_review": ("requirements", "review_status", "accepted"),
             "section_review": ("proposal_sections", "review_status", "approved"),
             "notice_form_review": ("form_fillings", "review_status", "approved")}
    if action != "source_review" and action not in kinds:
        return details
    approved = inputs.get("source_reviewed") is True if action == "source_review" else False
    if action in kinds:
        collection, key, value = kinds[action]
        previous = {x.get("id", x.get("document_id")): x for x in details.get("previous_inputs", {}).get(collection, [])}
        approved = any(x.get(key) == value and x != previous.get(x.get("id", x.get("document_id")))
                       for x in inputs.get(collection, []))
    return {**details, "brief_snapshot": review_snapshot(inputs), "brief_approved": approved}


def public_brief(inputs: dict, history: list) -> dict:
    brief = build(inputs)
    has_approval = (inputs.get("source_reviewed") is True
        or any(d.get("confirmed") is True for d in inputs.get("documents", []))
        or any(r.get("review_status") == "accepted" for r in inputs.get("requirements", []))
        or any(s.get("review_status") == "approved" for k in ("proposal_sections", "form_fillings") for s in inputs.get(k, [])))
    reviewed = next((r for r in history if (r["details"] or {}).get("brief_approved") is not False and r["action"] in {
        "source_review", "evidence_review", "requirement_review", "section_review", "notice_form_review"
    }), None) if has_approval else None
    before = (reviewed["details"] or {}).get("brief_snapshot") if reviewed else None
    brief["review_comparison"] = ("none" if reviewed is None else "unavailable" if not before
        else "unchanged" if before.get("signature") == brief["signature"] else "updated")
    return brief


def public_reviews(history: list) -> list[dict]:
    return [{**{k: r[k] for k in ("id", "job_id", "action", "note", "input_version", "created_at")},
             "actor": (r["details"] or {}).get("actor"),
             "brief_snapshot": (r["details"] or {}).get("brief_snapshot"),
             "output_sha256": (r["details"] or {}).get("sha256"),
             "layout_confirmed": bool((r["details"] or {}).get("layout_confirmed"))}
            for r in history]
