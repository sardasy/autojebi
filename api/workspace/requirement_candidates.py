"""Bounded, exact-source hints for human requirement recovery; no model calls or writes."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

MAX_CHARACTERS = 150_000
MAX_CANDIDATES = 100
MAX_QUOTE = 4000

_MANDATORY = re.compile(r"하여야|해야|되어야|이어야|필수|의무|할\s*것|금지|허용하지|불가|제외한다|포함하지")
_QUANTITY = re.compile(r"(?:수량|납품|구매|공급|설치|장비|제품).{0,80}?\d[\d,.]*\s*(?:대|개|식|세트|조|본|매|EA|SET)(?![A-Za-z])", re.IGNORECASE)
_DEADLINE = re.compile(r"(?:납기|기한|마감|제출|계약일|납품).{0,80}?(?:\d[\d.\- /:]*\s*(?:일|시간|개월|주)|\d{4}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{1,2}|\d{1,2}:\d{2}|까지|이내)")
_SUBMISSION = re.compile(r"제출.{0,60}?(?:하여야|해야|필수|한다|함|할\s*것)|(?:제출\s*서류|구비\s*서류)\s*[:：]")


class RequirementCandidate(BaseModel):
    id: str
    document_id: str
    document_name: str
    document_sha256: str | None
    source_text_sha256: str
    text: str
    quote: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    locator: str
    category: Literal["technical", "qualification", "document", "schedule"]
    signals: list[str]


class RequirementCandidatesResponse(BaseModel):
    version: int
    items: list[RequirementCandidate]
    scanned_characters: int
    source_document_count: int
    limited: bool
    warnings: list[str]


def find_candidates(inputs: dict, version: int) -> RequirementCandidatesResponse:
    sources = [doc for doc in inputs.get("documents", []) if doc.get("role") == "notice_source"]
    result = RequirementCandidatesResponse(version=version, items=[], scanned_characters=0,
        source_document_count=len(sources), limited=False, warnings=[])
    for doc in sources:
        text = doc.get("text")
        if not isinstance(text, str) or not text.strip() or not doc.get("id"):
            result.warnings.append("본문이 없는 공고 원문은 후보를 찾지 못했습니다.")
            continue
        remaining = MAX_CHARACTERS - result.scanned_characters
        if remaining <= 0 or len(result.items) >= MAX_CANDIDATES:
            result.limited = True
            break
        bounded = text[:remaining]
        result.scanned_characters += len(bounded)
        if len(text) > remaining:
            result.limited = True
            # Do not offer a cut-off line: its tail may contain an exception or negation.
            if not bounded.endswith(("\r", "\n")):
                boundary = max(bounded.rfind("\r"), bounded.rfind("\n"))
                bounded = bounded[:boundary + 1]
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if (doc.get("extraction", {}).get("complete") is False
                and doc.get("text_origin") != "manual_confirmed"):
            result.warnings.append("일부 추출이 끝나지 않은 원문이 있습니다. 누락된 페이지와 첨부를 직접 확인하세요.")
        if not doc.get("sha256"):
            result.warnings.append("파일 해시가 없는 원문이 있습니다. 원본 파일도 대조하세요.")
        offset = 0
        for line_no, raw_line in enumerate(bounded.splitlines(keepends=True), start=1):
            quote = raw_line.strip()
            start = offset + len(raw_line) - len(raw_line.lstrip())
            offset += len(raw_line)
            if not quote:
                continue
            if len(quote) > MAX_QUOTE:
                result.warnings.append("4,000자를 넘는 행은 조건이 잘리지 않도록 건너뛰었습니다.")
                continue
            signals = [name for name, pattern in (("의무·제한", _MANDATORY), ("수량", _QUANTITY),
                ("기한", _DEADLINE), ("제출", _SUBMISSION)) if pattern.search(quote)]
            if not signals:
                continue
            category = "schedule" if "기한" in signals else "document" if "제출" in signals else (
                "qualification" if re.search(r"자격|면허|등록증|인증서|사업자등록", quote) else "technical")
            end = start + len(quote)
            signature = f"{doc['id']}:{checksum}:{start}:{end}"
            result.items.append(RequirementCandidate(id=hashlib.sha256(signature.encode()).hexdigest(),
                document_id=str(doc["id"]), document_name=str(doc.get("name") or "공고 원문"),
                document_sha256=doc.get("sha256"), source_text_sha256=checksum,
                text=quote, quote=quote, start=start, end=end, locator=f"본문 {line_no}행 · 문자 {start}~{end}",
                category=category, signals=signals))
            if len(result.items) >= MAX_CANDIDATES:
                result.limited = True
                break
    if result.limited:
        result.warnings.append("최대 100개 후보·총 150,000자 범위만 확인했습니다. 나머지 원문도 직접 검토하세요.")
    result.warnings = list(dict.fromkeys(result.warnings))
    return result
