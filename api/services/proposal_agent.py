from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from api.models.proposals import (
    NoticeRequirementRecord,
    ProposalCoverageItem,
    ProposalSectionRecord,
    RequirementEvidenceRecord,
)

SECTION_BY_TYPE = {
    "company_overview": ("company_overview", "회사 일반현황"),
    "similar_experience": ("similar_projects", "유사 사업 수행실적"),
    "technical_strength": ("technical_strength", "기술적 차별성"),
    "execution_plan": ("execution_plan", "사업 수행방안"),
    "maintenance": ("maintenance", "유지보수 계획"),
    "quality": ("quality", "품질관리"),
    "security": ("security", "보안관리"),
    "qualification": ("qualification", "자격 및 인증"),
    "documents": ("documents", "제출서류 대응"),
    "other": ("other", "기타 요구사항"),
}

TYPE_KEYWORDS = {
    "company_overview": ["회사", "일반현황", "조직", "인력", "전문"],
    "similar_experience": ["실적", "수행", "구축", "납품", "경험", "최근 3년"],
    "technical_strength": ["기술", "규격", "성능", "차별", "HIL", "Typhoon", "PLECS", "전력전자"],
    "execution_plan": ["수행방안", "일정", "납품", "설치", "교육", "지원"],
    "maintenance": ["유지보수", "하자", "A/S", "지원", "장애"],
    "quality": ["품질", "검수", "시험", "성능검사", "보증"],
    "security": ["보안", "개인정보", "정보보호", "자료관리"],
    "qualification": ["자격", "인증", "면허", "등록", "직접생산"],
    "documents": ["제출서류", "서류", "제안서", "증빙", "첨부"],
}


def extract_requirements_from_notice(row: Any, spec_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = dict(row["raw"] or {})
    analysis = dict(row["analysis"] or {})
    document_automation = analysis.get("document_automation") if isinstance(analysis, dict) else None
    texts = [
        str(row["title"] or ""),
        str(row.get("category") or ""),
        str(raw.get("bidNtceNm") or ""),
        str(raw.get("ntceSpecFileNm1") or ""),
        str(raw.get("cntrctCnclsMthdNm") or ""),
    ]
    if isinstance(document_automation, dict):
        for item in document_automation.get("checklist") or []:
            if isinstance(item, dict):
                texts.append(str(item.get("name") or ""))
                texts.append(str(item.get("reason") or ""))
    for item in spec_rows:
        texts.append(str(item.get("label") or ""))
        texts.append(str(item.get("required_value") or ""))
        texts.append(str(item.get("source_text") or ""))
    corpus = "\n".join(part for part in texts if part.strip())

    requirements: list[dict[str, Any]] = []
    for req_type, keywords in TYPE_KEYWORDS.items():
        if req_type in {"company_overview", "documents"} or _contains_any(corpus, keywords):
            requirements.append(
                {
                    "section": SECTION_BY_TYPE[req_type][1],
                    "requirement_type": req_type,
                    "requirement_text": _requirement_text(req_type, corpus),
                    "mandatory": req_type not in {"other"},
                    "evaluation_score": None,
                    "source_page": None,
                    "extracted_data": {"keywords": [kw for kw in keywords if kw.lower() in corpus.lower()]},
                }
            )
    if not any(item["requirement_type"] == "technical_strength" for item in requirements):
        requirements.append(
            {
                "section": "기술적 차별성",
                "requirement_type": "technical_strength",
                "requirement_text": "공고 규격에 부합하는 기술 대응 방안을 제시해야 합니다.",
                "mandatory": True,
                "evaluation_score": None,
                "source_page": None,
                "extracted_data": {"fallback": True},
            }
        )
    return requirements


def score_chunk(requirement: dict[str, Any], chunk: dict[str, Any], document: dict[str, Any]) -> float:
    req_text = str(requirement.get("requirement_text") or "")
    req_type = str(requirement.get("requirement_type") or "other")
    haystack = " ".join(
        str(value or "")
        for value in (
            document.get("title"),
            document.get("category"),
            document.get("project_name"),
            document.get("customer_name"),
            chunk.get("heading"),
            chunk.get("content"),
        )
    )
    tokens = set(_tokens(req_text))
    keyword_hits = sum(1 for kw in TYPE_KEYWORDS.get(req_type, []) if kw.lower() in haystack.lower())
    token_hits = len(tokens.intersection(_tokens(haystack)))
    category_bonus = 1 if document.get("category") in {"proposal", "report", "product", "company"} else 0
    score = min(1.0, (keyword_hits * 0.18) + (token_hits * 0.08) + (category_bonus * 0.12))
    return round(score, 4)


def score_performance(requirement: dict[str, Any], performance: dict[str, Any]) -> float:
    req_type = str(requirement.get("requirement_type") or "")
    haystack = " ".join(
        str(value or "")
        for value in (
            performance.get("project_name"),
            performance.get("customer_name"),
            performance.get("project_type"),
            performance.get("description"),
            " ".join(performance.get("technologies") or []),
            " ".join(performance.get("products") or []),
        )
    )
    keyword_hits = sum(1 for kw in TYPE_KEYWORDS.get(req_type, []) if kw.lower() in haystack.lower())
    verified_bonus = 0.2 if performance.get("verified") else 0.0
    type_bonus = 0.25 if req_type == "similar_experience" else 0.05
    return round(min(1.0, keyword_hits * 0.18 + verified_bonus + type_bonus), 4)


def build_section(
    *,
    notice_no: str,
    section_key: str,
    section_title: str,
    requirements: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence_ids = [str(item["id"]) for item in evidences]
    if evidences:
        claims = []
        for req in requirements:
            top = [e for e in evidences if e.get("requirement_id") == req.get("id")][:2]
            refs = ", ".join(str(e["id"]) for e in top)
            if top:
                claims.append(
                    f"{req['requirement_text']}에 대해 보유 자료를 근거로 대응 가능합니다. [Evidence: {refs}]"
                )
            else:
                claims.append(f"{req['requirement_text']}에 대한 구체 근거는 추가 확인이 필요합니다. [검증필요]")
        content = "\n".join(claims)
        confidence = sum(float(e.get("confidence_score") or 0) for e in evidences) / len(evidences)
    else:
        content = f"{section_title} 항목은 현재 연결된 Evidence가 없어 담당자 검토가 필요합니다. [검증필요]"
        confidence = 0.0
    return {
        "notice_no": notice_no,
        "template_key": "proposal",
        "section_key": section_key,
        "section_title": section_title,
        "generated_content": content,
        "generation_status": "draft",
        "evidence_ids": evidence_ids,
        "confidence_score": round(confidence, 4),
        "fact_check_status": "pending",
        "fact_check_notes": [],
        "human_approved": False,
        "version": 1,
    }


def verify_sections(sections: list[dict[str, Any]], evidence_ids: set[str]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for section in sections:
        content = str(section.get("generated_content") or "")
        notes: list[dict[str, Any]] = []
        refs = set(re.findall(r"Evidence:\s*([^\]]+)", content))
        expanded_refs = {
            item.strip()
            for group in refs
            for item in group.split(",")
            if item.strip()
        }
        if "[검증필요]" in content:
            notes.append({"severity": "warning", "detail": "검증필요 문구가 남아 있습니다."})
        missing_refs = sorted(ref for ref in expanded_refs if ref not in evidence_ids)
        if missing_refs:
            notes.append({"severity": "error", "detail": f"존재하지 않는 Evidence 참조: {', '.join(missing_refs)}"})
        status = "reject" if any(n["severity"] == "error" for n in notes) else "warning" if notes else "pass"
        updated = dict(section)
        updated["fact_check_status"] = status
        updated["fact_check_notes"] = notes
        updated["generation_status"] = "verified" if status == "pass" else "draft"
        verified.append(updated)
    return verified


def coverage_items(
    requirements: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
) -> tuple[int, list[ProposalCoverageItem]]:
    by_req: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evidence in evidences:
        by_req[str(evidence.get("requirement_id"))].append(evidence)

    items: list[ProposalCoverageItem] = []
    total_weight = 0
    earned = 0
    for req in requirements:
        req_id = str(req["id"])
        count = len(by_req.get(req_id, []))
        status = "ready" if count >= 3 else "partial" if count > 0 else "missing"
        weight = 2 if req.get("mandatory") else 1
        total_weight += weight
        earned += weight if status == "ready" else 1 if status == "partial" else 0
        items.append(
            ProposalCoverageItem(
                requirement_id=req_id,
                requirement_type=req["requirement_type"],
                requirement_text=str(req["requirement_text"]),
                mandatory=bool(req.get("mandatory")),
                evidence_count=count,
                status=status,
            )
        )
    score = int(round((earned / total_weight) * 100)) if total_weight else 0
    return score, items


def row_to_requirement(row: dict[str, Any]) -> NoticeRequirementRecord:
    return NoticeRequirementRecord(
        id=str(row["id"]),
        notice_no=str(row["notice_no"]),
        section=str(row["section"]),
        requirement_type=row["requirement_type"],
        requirement_text=str(row["requirement_text"]),
        mandatory=bool(row["mandatory"]),
        evaluation_score=_float_or_none(row.get("evaluation_score")),
        source_page=row.get("source_page"),
        extracted_data=dict(row.get("extracted_data") or {}),
    )


def row_to_evidence(row: dict[str, Any]) -> RequirementEvidenceRecord:
    return RequirementEvidenceRecord(
        id=str(row["id"]),
        requirement_id=str(row["requirement_id"]),
        document_id=row.get("document_id"),
        chunk_id=row.get("chunk_id"),
        performance_id=row.get("performance_id"),
        evidence_type=str(row["evidence_type"]),
        relevance_score=float(row.get("relevance_score") or 0),
        confidence_score=float(row.get("confidence_score") or 0),
        quoted_text=str(row["quoted_text"]),
        reasoning_summary=row.get("reasoning_summary"),
        approved=bool(row.get("approved")),
    )


def row_to_section(row: dict[str, Any]) -> ProposalSectionRecord:
    return ProposalSectionRecord(
        id=str(row["id"]),
        notice_no=str(row["notice_no"]),
        template_key=str(row.get("template_key") or "proposal"),
        section_key=str(row["section_key"]),
        section_title=str(row["section_title"]),
        generated_content=str(row["generated_content"]),
        generation_status=str(row["generation_status"]),
        evidence_ids=list(row.get("evidence_ids") or []),
        confidence_score=float(row.get("confidence_score") or 0),
        fact_check_status=row.get("fact_check_status") or "pending",
        fact_check_notes=list(row.get("fact_check_notes") or []),
        human_approved=bool(row.get("human_approved")),
        version=int(row.get("version") or 1),
    )


def _requirement_text(req_type: str, corpus: str) -> str:
    defaults = {
        "company_overview": "회사 일반현황과 전력전자 분야 수행 역량을 제시해야 합니다.",
        "similar_experience": "유사 사업 수행실적과 납품 경험을 제시해야 합니다.",
        "technical_strength": "공고 요구 규격에 부합하는 기술적 차별성과 대응 방안을 제시해야 합니다.",
        "execution_plan": "납품, 설치, 교육, 기술지원 등 사업 수행방안을 제시해야 합니다.",
        "maintenance": "유지보수 및 장애 대응 계획을 제시해야 합니다.",
        "quality": "품질관리, 검수, 시험 및 보증 계획을 제시해야 합니다.",
        "security": "보안관리 및 자료관리 방안을 제시해야 합니다.",
        "qualification": "입찰 참여에 필요한 자격, 인증, 등록 조건을 충족해야 합니다.",
        "documents": "필수 제출서류와 증빙자료를 누락 없이 준비해야 합니다.",
    }
    return defaults.get(req_type, _compact(corpus, 300) or "기타 요구사항을 검토해야 합니다.")


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9가-힣]{2,}", text)]


def _compact(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "..."


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)
