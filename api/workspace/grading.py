"""Snapshot-only grading; references never imply human compliance or a decision.

All scores (including fit_score/score_total) use 0..1; missing axes are None.
commercial.offer_price is the total offer in KRW, not a unit or recommended bid price.
quantity is provenance metadata and is not multiplied into that total.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

from api.collector.g2b_client import G2BClient
from api.config import settings
from api.grading.schemas import QualificationInfo
from api.grading.scorer import combine
from api.sku.qdrant_store import QdrantStore
from api.workspace.provenance import price_amount_present, requirement_valid, source_quote_valid

_LIMIT = 5


def _positive_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() and number > 0 else None


def _axis(score: float | None, code: str, reason: str, **details: Any) -> dict:
    return {
        "state": "evaluated" if score is not None else "unassessed",
        "score": score,
        "reason_code": code,
        "reason": reason,
        **details,
    }


def _requirement_axis(requirements: list[dict], documents: dict[str, dict]) -> dict:
    assessed, missing, evidence_count = [], [], 0
    for requirement in requirements:
        valid = requirement_valid(requirement, documents)
        evidence_count += int(valid)
        compliance = requirement.get("compliance", "unassessed")
        if not valid or compliance not in {"meets", "does_not_meet"}:
            missing.append(
                {
                    "requirement_id": requirement.get("id"),
                    "reason_code": "invalid_provenance" if not valid else "compliance_pending",
                }
            )
        else:
            assessed.append(requirement)
    details = {
        "requirement_count": len(requirements),
        "evidence_valid_count": evidence_count,
        "assessed_count": len(assessed),
        "meets_count": sum(r["compliance"] == "meets" for r in assessed),
        "does_not_meet_ids": [r.get("id") for r in assessed if r["compliance"] == "does_not_meet"],
        "unassessed_requirements": missing,
    }
    if not requirements:
        return _axis(None, "requirements_missing", "해당 축의 요구사항이 없습니다.", **details)
    if missing:
        return _axis(
            None,
            "assessment_incomplete",
            "모든 요구사항의 근거와 담당자 충족 판정이 필요합니다.",
            **details,
        )
    mandatory_failed = any(
        r.get("mandatory", True) and r["compliance"] == "does_not_meet" for r in assessed
    )
    score = 0.0 if mandatory_failed else details["meets_count"] / len(requirements)
    return _axis(
        score,
        "mandatory_not_met" if mandatory_failed else "human_compliance",
        "필수 요구사항 미충족입니다."
        if mandatory_failed
        else "담당자가 판정한 요구사항 충족 비율입니다.",
        **details,
    )


def _price_axis(snapshot: dict, documents: dict[str, dict]) -> dict:
    commercial = snapshot.get("commercial") or {}
    offer = _positive_decimal(commercial.get("offer_price"))
    quantity = commercial.get("quantity")
    base = _positive_decimal((snapshot.get("notice") or {}).get("base_price"))
    if offer is None or type(quantity) is not int or quantity <= 0:
        return _axis(None, "offer_missing_or_invalid", "양수 제안 총액과 정수 수량이 필요합니다.")
    document = documents.get(commercial.get("document_id")) or {}
    quote = commercial.get("quote") or ""
    if not (
        document.get("role") in {"company_evidence", "product_evidence"}
        and document.get("confirmed")
        and isinstance(quote, str)
        and quote.strip()
        and quote in (document.get("text") or "")
        and str(commercial.get("locator") or "").strip()
    ):
        return _axis(
            None, "offer_evidence_invalid", "제안 금액의 확인된 증빙과 인용 위치가 필요합니다."
        )
    if not price_amount_present(quote, offer):
        return _axis(
            None, "offer_quote_mismatch", "인용문에서 동일한 원화 제안 금액을 확인할 수 없습니다."
        )
    if base is None:
        return _axis(
            None, "base_price_missing_or_invalid", "공고의 확인 가능한 양수 기초금액이 없습니다."
        )
    return _axis(
        1.0 if offer <= base else 0.0,
        "within_budget" if offer <= base else "over_budget",
        "제안 총액과 공고 기초금액의 단순 예산 비교입니다. 추천 투찰가가 아닙니다.",
        basis="total_offer_vs_notice_base_price",
        currency="KRW",
        offer_price=float(offer),
        base_price=float(base),
        quantity=quantity,
        source={key: commercial.get(key) for key in ("document_id", "quote", "locator", "note")},
    )


def _sku_references(requirements: list[dict], documents: dict[str, dict]) -> dict:
    queries = []
    seen = set()
    for requirement in requirements:
        if not source_quote_valid(requirement, documents):
            continue
        quote = requirement["quote"]
        if quote in seen:
            continue
        seen.add(quote)
        queries.append(
            {
                "query": quote,
                "requirement_id": requirement.get("id"),
                "document_id": requirement["document_id"],
                "quote": quote,
                "locator": requirement["locator"],
            }
        )
    result = {
        "source": "qdrant",
        "state": "not_queried",
        "reason_code": "grounded_technical_text_missing",
        "reason": "원문에서 확인된 기술 요구사항 인용이 없어 검색하지 않았습니다.",
        "queries": queries[:_LIMIT],
        "omitted_query_count": max(0, len(queries) - _LIMIT),
        "limit": _LIMIT,
        "candidates": [],
        "warnings": [],
    }
    if not queries:
        return result
    if result["omitted_query_count"]:
        result["warnings"].append("SKU 참고 검색은 원문 인용 5개로 제한되었습니다.")
    store = None
    stage = "constructor_failed"
    try:
        store = QdrantStore()
        stage = "collection_unavailable"
        if not store.collection_exists():
            raise RuntimeError("collection unavailable")
        result["collection"] = store.collection
        stage = "search_failed"
        candidates = []
        for source in result["queries"]:
            for match in store.search(source["query"], limit=_LIMIT):
                candidates.append(
                    {
                        "sku": match.sku.model_dump(mode="json"),
                        "similarity": match.score,
                        "source": {"type": "qdrant", "collection": store.collection, **source},
                        "review_status": "pending",
                    }
                )
        # Ranking is only for discovery; this number never reaches a scoring function.
        ranked = sorted(candidates, key=lambda candidate: candidate["similarity"], reverse=True)
        unique = {}
        for candidate in ranked:
            unique.setdefault(candidate["sku"]["sku_id"], candidate)
        result.update(
            state="available" if candidates else "no_matches",
            reason_code="pending_human_confirmation" if candidates else "no_matches",
            reason="SKU 검색 결과는 담당자의 제품 적합성 확인이 필요합니다."
            if candidates
            else "일치하는 SKU 참고자료가 없습니다.",
            candidates=list(unique.values())[:_LIMIT],
        )
    except Exception:
        result.update(
            state="unavailable",
            reason_code=stage,
            reason="SKU 저장소 또는 검색 결과를 확인할 수 없습니다.",
            candidates=[],
        )
    finally:
        if store is not None:
            try:
                close = getattr(store, "close", None)
                if close is not None:
                    close()
                else:
                    # Older injected store doubles expose only the underlying client.
                    store._client.close()
            except Exception:
                result["warnings"].append("SKU 조회 연결 종료를 확인할 수 없습니다.")
    return result


def _qualification_references(notice: dict) -> dict:
    bid_no, bid_seq = notice.get("bid_no"), notice.get("bid_seq")
    result = {
        "source": "g2b",
        "state": "not_configured",
        "reason_code": "api_key_missing",
        "reason": "G2B API 키가 없어 자격 참고자료를 조회하지 않았습니다.",
        "review_status": "pending",
        "bid_no": bid_no,
        "bid_seq": bid_seq,
        "references": None,
        "warnings": [],
    }
    if not settings.data_go_kr_api_key.strip():
        return result
    if not all(isinstance(value, str) and value.strip() for value in (bid_no, bid_seq)):
        result.update(
            state="not_queried",
            reason_code="notice_identity_missing",
            reason="정확한 공고번호와 공고차수가 없어 자격 참고자료를 조회하지 않았습니다.",
        )
        return result

    async def fetch() -> QualificationInfo:
        client = G2BClient()
        try:
            return await client.fetch_qualifications(bid_no, bid_seq)
        finally:
            try:
                await client.aclose()
            except Exception:
                result["warnings"].append("G2B 조회 연결 종료를 확인할 수 없습니다.")

    try:
        # grade is the synchronous worker entry point; never leak a coroutine in a running loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("synchronous worker context required")
        info = QualificationInfo.model_validate(asyncio.run(fetch()))
        if info.error is not None or (info.bid_no, info.bid_seq) != (bid_no, bid_seq):
            raise ValueError("unverified qualification response")
        references = {
            "licenses": info.licenses,
            "regions": info.regions,
            "permitted_industries": info.permitted_industries,
        }
        result.update(
            state="pending_human_confirmation" if any(references.values()) else "no_references",
            reason_code="human_confirmation_required",
            reason="자격 조회 결과는 담당자 확인이 필요하며, 빈 응답도 자격 통과를 뜻하지 않습니다.",
            references=references,
        )
    except Exception:
        result.update(
            state="unavailable",
            reason_code="qualification_lookup_failed",
            reason="G2B 자격 참고자료를 확인할 수 없습니다. 담당자 확인이 필요합니다.",
        )
    return result


def grade(engine: Any, job: dict) -> dict:
    """Assess job['snapshot'] in the synchronous worker; engine is intentionally unused.

    Read requirements, documents, commercial, and notice.{base_price,bid_no,bid_seq}.
    Return axes.{spec,qualification,price} with state, score, reason_code, and reason;
    flat score_spec/qualification_score/price_score mirror those scores. fit_score
    and score_total mirror combine().total only when all three axes are evaluated.
    technical_coverage counts valid evidence; technical_assessment_coverage counts
    explicit compliance assessments. Both are None when no technical items exist.
    sku_search and qualification_references are advisory lookup reports, never gates
    on human assessments. This function never updates legacy status or v2 decisions.
    """
    snapshot = job["snapshot"]
    requirements = snapshot.get("requirements") or []
    documents = {document["id"]: document for document in snapshot.get("documents") or []}
    technical = [r for r in requirements if r.get("category") == "technical"]
    qualification = [r for r in requirements if r.get("category") == "qualification"]
    spec = _requirement_axis(technical, documents)
    qual = _requirement_axis(qualification, documents)
    price = _price_axis(snapshot, documents)
    sku = _sku_references(technical, documents)
    references = _qualification_references(snapshot.get("notice") or {})
    axes = {"spec": spec, "qualification": qual, "price": price}
    breakdown = None
    if all(axis["score"] is not None for axis in axes.values()):
        breakdown = combine(spec["score"], qual["score"], price["score"]).model_dump(mode="json")
    total = breakdown["total"] if breakdown else None
    warnings = [axis["reason"] for axis in axes.values() if axis["state"] == "unassessed"]
    warnings.extend(
        [sku["reason"], references["reason"], *sku["warnings"], *references["warnings"]]
    )
    return {
        "fit_score": total,
        "score_total": total,
        "score_scale": "0..1",
        "score_spec": spec["score"],
        "qualification_score": qual["score"],
        "price_score": price["score"],
        "technical_coverage": spec["evidence_valid_count"] / len(technical) if technical else None,
        "technical_assessment_coverage": spec["assessed_count"] / len(technical)
        if technical
        else None,
        "axes": axes,
        "breakdown": breakdown,
        "candidates": sku["candidates"],
        "sku_search": sku,
        "qualification_references": references,
        "warnings": list(dict.fromkeys(warnings)),
    }
