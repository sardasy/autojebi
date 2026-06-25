"""필요서류 자동확인 — 첨부 본문에서 제출서류를 제출시점(stage)별로 추출·분류.

파이프라인(파일 IO는 라우터가 담당하고, 이 모듈은 순수 텍스트→구조화):
  file_pages([{source_file, page_no, text}])
    → find_candidate_segments()   키워드 포함 문장 후보만 추림(전체 본문 LLM 투입 회피)
    → classify_required_documents() LLM이 doc_name/requirement_type/submit_stage/근거 분류
    → 정규화된 행(dict) 리스트
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from api.config import settings

log = logging.getLogger(__name__)

# §2 제출서류 탐색 키워드 (문장 후보 선별용)
KEYWORDS: tuple[str, ...] = (
    "제출서류", "구비서류", "입찰등록서류", "입찰참가자격", "참가자격",
    "제안서 제출", "제안서", "발표자료", "가격제안서", "산출내역서", "견적서",
    "규격서", "기술자료", "카탈로그", "사양서", "납품실적", "실적증명서",
    "중소기업확인서", "직접생산확인증명서", "사업자등록증", "법인등기부등본",
    "인감증명서", "사용인감계", "위임장", "청렴계약이행각서", "보안서약서",
    "확약서", "착수계", "납품계획서", "제출하여야", "제출해야", "낙찰자",
    "계약상대자", "계약 체결 전", "대리인",
)

SUBMIT_STAGES: frozenset[str] = frozenset(
    {"bid", "proposal", "price", "post_award", "contract", "delivery", "conditional"}
)
REQUIREMENT_TYPES: frozenset[str] = frozenset(
    {"required", "conditional", "winner_only", "contract_stage", "reference"}
)


def find_candidate_segments(
    file_pages: list[dict[str, Any]],
    *,
    max_segments: int = 60,
) -> list[dict[str, Any]]:
    """페이지 텍스트에서 키워드를 포함한 문장 ±전후문맥 윈도우만 수집.

    file_pages: [{"source_file": str, "page_no": int|None, "text": str}]
    반환: [{"source_file", "page_no", "text"}] (중복 제거, max_segments 캡)
    """
    segments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fp in file_pages:
        text = str(fp.get("text") or "")
        if not text:
            continue
        lines = [ln.strip() for ln in re.split(r"[\n\r]+", text) if ln.strip()]
        for i, line in enumerate(lines):
            if not any(kw in line for kw in KEYWORDS):
                continue
            ctx = " ".join(lines[max(0, i - 1) : i + 2])[:600]
            key = ctx[:120]
            if key in seen:
                continue
            seen.add(key)
            segments.append(
                {
                    "source_file": fp.get("source_file"),
                    "page_no": fp.get("page_no"),
                    "text": ctx,
                }
            )
            if len(segments) >= max_segments:
                return segments
    return segments


def _safe_json_array(text: str) -> list[Any]:
    cleaned = text.replace("```json", "").replace("```", "")
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        value = json.loads(cleaned[start : end + 1])
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


_PROMPT_HEADER = (
    "다음은 나라장터 입찰공고 첨부문서에서 추출한 '제출서류 후보 문단'입니다.\n\n"
    "목표: 입찰 참여에 필요한 제출서류를 빠짐없이 추출하세요.\n\n"
    "requirement_type 분류:\n"
    "- required: 반드시 제출\n"
    "- conditional: 조건부 제출(대리인/공동수급/해당 시 등)\n"
    "- winner_only: 낙찰자만 제출\n"
    "- contract_stage: 계약 단계 제출\n"
    "- reference: 참고자료(제출서류 아님)\n\n"
    "submit_stage 분류(제출 시점):\n"
    "- bid: 입찰/투찰/참가신청 시\n"
    "- proposal: 제안서/발표자료/정량평가자료 제출 시\n"
    "- price: 가격제안서/산출내역서/견적서 제출 시\n"
    "- post_award: 낙찰 후(낙찰자/계약상대자/계약 체결 전)\n"
    "- contract: 계약 후(착수계/보안서약서/납품계획서)\n"
    "- delivery: 납품/검수 단계\n"
    "- conditional: 시점이 조건부\n\n"
    "출력은 JSON 배열만(설명/마크다운/코드펜스 없이). 각 원소 필드:\n"
    "doc_name, requirement_type, submit_stage, source_file, page_no, deadline, "
    "condition, evidence_text, confidence(0~1).\n"
    "source_file/page_no는 각 문단 앞의 [파일명 p번호] 표식에서 가져오세요.\n\n"
    "후보 문단:\n"
)


def classify_required_documents(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """후보 문단을 LLM으로 분류해 정규화된 제출서류 행 리스트 반환."""
    if not candidates or not settings.anthropic_api_key.strip():
        return []
    blob = "\n".join(
        f"[{c.get('source_file') or '첨부'} p{c.get('page_no') if c.get('page_no') is not None else '-'}] {c.get('text')}"
        for c in candidates
    )[:14000]
    prompt = _PROMPT_HEADER + blob
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": prompt},
                # prefill "[" — Haiku가 산문 대신 JSON 배열로 응답하도록 강제.
                {"role": "assistant", "content": "["},
            ],
        )
        body_text = "\n".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        items = _safe_json_array("[" + body_text)
    except Exception as exc:  # noqa: BLE001
        log.warning("[required_documents] LLM classify failed: %s", exc)
        return []

    return _normalize(items)


def _normalize(items: list[Any]) -> list[dict[str, Any]]:
    """LLM 출력 → 테이블 행. doc_name+submit_stage로 중복 병합(최대 confidence 유지)."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        doc_name = str(raw.get("doc_name") or "").strip()
        if not doc_name:
            continue
        req_type = str(raw.get("requirement_type") or "required").strip()
        if req_type not in REQUIREMENT_TYPES:
            req_type = "required"
        stage = str(raw.get("submit_stage") or "bid").strip()
        if stage not in SUBMIT_STAGES:
            stage = "conditional" if req_type == "conditional" else "bid"
        try:
            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        page_no = raw.get("page_no")
        try:
            page_no = int(page_no) if page_no not in (None, "", "-") else None
        except (TypeError, ValueError):
            page_no = None
        row = {
            "doc_name": doc_name[:200],
            "requirement_type": req_type,
            "submit_stage": stage,
            "source_file": (str(raw.get("source_file")).strip()[:200]
                            if raw.get("source_file") else None),
            "page_no": page_no,
            "deadline": (str(raw.get("deadline")).strip()[:200]
                         if raw.get("deadline") else None),
            "condition": (str(raw.get("condition")).strip()[:300]
                          if raw.get("condition") else None),
            "evidence_text": (str(raw.get("evidence_text")).strip()[:1000]
                              if raw.get("evidence_text") else None),
            "confidence": round(confidence, 3),
        }
        key = (doc_name[:200], stage)
        prev = merged.get(key)
        if prev is None or row["confidence"] > prev["confidence"]:
            merged[key] = row
    # 제출시점 우선순위로 정렬(지금 준비할 것 우선)
    order = {"bid": 0, "proposal": 1, "price": 2, "conditional": 3,
             "post_award": 4, "contract": 5, "delivery": 6}
    return sorted(
        merged.values(),
        key=lambda r: (order.get(r["submit_stage"], 9), -r["confidence"]),
    )
