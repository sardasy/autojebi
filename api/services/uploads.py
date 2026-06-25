"""사용자 업로드 파일 저장소 (M11 — 서류 자동화 v2).

로컬 파일시스템 기반. 메타데이터는 `analysis.document_automation.uploads[]`에 누적.

규칙:
- 저장 경로: ``<UPLOAD_DIR>/<notice_no>/<uuid>.<ext>`` (notice_no는 path-safe로 sanitize)
- 파일명 충돌 회피: uuid4
- 확장자 검증: `settings.upload_allowed_ext_set`
- 사이즈 검증: `settings.upload_max_bytes`
- 디스크에 쓰면서 sha256/byte 카운팅 → 메타데이터로 반환

라우터/문서 자동화 모듈에서 호출되는 순수 함수 모음.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException

from api.config import settings
from api.llm.extractor import extract_pdf_text
from api.models.notices import UploadedDocument
from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError

log = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.\-]")
_CHUNK = 64 * 1024
AUTO_READY_THRESHOLD = 0.75


@dataclass(frozen=True)
class SavedFile:
    storage_path: str
    size: int
    sha256: str


class UploadError(HTTPException):
    """HTTPException 서브클래스 — 라우터에서 그대로 raise."""


def base_dir() -> Path:
    """업로드 루트 디렉터리. 빈값이면 시스템 temp 하위로 생성."""
    root = settings.upload_dir.strip() or os.path.join(
        tempfile.gettempdir(), "autojebi", "uploads"
    )
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def notice_dir(notice_no: str) -> Path:
    """공고별 하위 디렉터리. notice_no는 path traversal 방지로 sanitize."""
    safe = _SAFE_NAME_RE.sub("_", notice_no.strip()) or "unknown"
    path = base_dir() / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def common_dir() -> Path:
    path = base_dir() / "common"
    path.mkdir(parents=True, exist_ok=True)
    return path


def common_metadata_path() -> Path:
    return common_dir() / "metadata.json"


def validate_extension(filename: str) -> str:
    """확장자 검증. 허용 목록에 없으면 415 raise. 반환값: 점 없는 소문자 확장자."""
    if "." not in filename:
        raise UploadError(status_code=415, detail="filename has no extension")
    ext = filename.rsplit(".", 1)[-1].strip().lower()
    if ext not in settings.upload_allowed_ext_set:
        raise UploadError(
            status_code=415,
            detail=f"extension '{ext}' not allowed (allowed: {sorted(settings.upload_allowed_ext_set)})",
        )
    return ext


def save_stream(
    stream: BinaryIO,
    *,
    notice_no: str,
    original_name: str,
    max_bytes: int | None = None,
) -> SavedFile:
    """업로드 스트림을 디스크에 저장하면서 sha256/사이즈 동시 계산.

    `max_bytes` 초과 시 413 raise + 부분 파일 제거.
    """
    cap = max_bytes if max_bytes is not None else settings.upload_max_bytes
    ext = validate_extension(original_name)
    target = notice_dir(notice_no) / f"{uuid.uuid4().hex}.{ext}"

    hasher = hashlib.sha256()
    total = 0
    try:
        with target.open("wb") as f:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > cap:
                    raise UploadError(
                        status_code=413,
                        detail=f"upload exceeds max bytes ({cap})",
                    )
                hasher.update(chunk)
                f.write(chunk)
    except UploadError:
        target.unlink(missing_ok=True)
        raise
    except OSError as exc:  # disk full, perms, ...
        target.unlink(missing_ok=True)
        log.exception("[uploads] failed to write %s: %s", target, exc)
        raise UploadError(status_code=500, detail=f"failed to write upload: {exc}") from exc

    return SavedFile(storage_path=str(target), size=total, sha256=hasher.hexdigest())


def build_metadata(
    saved: SavedFile,
    *,
    original_name: str,
    mime: str | None,
    item_id: str | None,
    detected_item_id: str | None = None,
    detect_confidence: float | None = None,
    analysis_summary: str | None = None,
    text_excerpt: str | None = None,
    text_extract_error: str | None = None,
    source_ref: str | None = "uploaded",
) -> UploadedDocument:
    return UploadedDocument(
        id=uuid.uuid4().hex,
        name=original_name,
        size=saved.size,
        mime=(mime or _guess_mime(original_name)),
        item_id=item_id,
        storage_path=saved.storage_path,
        uploaded_at=datetime.now(tz=UTC).isoformat(),
        sha256=saved.sha256,
        detected_item_id=detected_item_id,
        detect_confidence=detect_confidence,
        analysis_summary=analysis_summary,
        text_excerpt=text_excerpt,
        text_extract_error=text_extract_error,
        source_ref=source_ref,  # type: ignore[arg-type]
    )


def analyze_upload(
    *,
    saved: SavedFile,
    original_name: str,
    checklist: list[dict] | None = None,
    explicit_item_id: str | None = None,
    hwp_client: HwpAgentClient | None = None,
    hwp_available: bool | None = None,
) -> dict[str, object]:
    """Extract a lightweight summary and recommend a checklist item.

    This is intentionally best-effort: bad PDFs, missing HWP agent, or unknown
    formats produce metadata instead of blocking the upload.

    ``hwp_available``: 호출자가 사전에 에이전트 health를 1회 확인한 결과. False면
    hwp/hwpx 파일에 대해 네트워크 호출을 건너뛰고 간결한 오류만 남긴다(파일마다
    connect 타임아웃 재시도로 시간 낭비하지 않도록). None이면 평소대로 시도한다.
    """
    ext = original_name.rsplit(".", 1)[-1].strip().lower() if "." in original_name else ""
    text = ""
    error: str | None = None

    if ext == "pdf":
        try:
            text = extract_pdf_text(Path(saved.storage_path).read_bytes())
        except Exception as exc:  # noqa: BLE001
            error = f"pdf text extraction failed: {exc}"
    elif ext in {"hwp", "hwpx"}:
        if hwp_available is False:
            error = "HWP 에이전트 미연결"
        else:
            try:
                client = hwp_client or HwpAgentClient()
                body = client.analyze_document(saved.storage_path)
                # milim-hwp-agent analyze-file은 본문을 text_preview(상위 N자)로 반환한다.
                # (text/body 키는 없음 → 과거엔 HWP 본문이 항상 빈값이었음)
                text = str(
                    body.get("text") or body.get("body") or body.get("text_preview") or ""
                )
                if not text:
                    placeholders = body.get("placeholders")
                    if placeholders:
                        text = "placeholders: " + ", ".join(str(p) for p in placeholders)
            except HwpAgentError as exc:
                error = f"hwp agent failed: {exc}"
            except Exception as exc:  # noqa: BLE001
                error = f"hwp analysis failed: {exc}"

    evidence = f"{original_name}\n{text}"
    detected_item_id, confidence = _detect_item(evidence, checklist or [])
    if explicit_item_id:
        item_id = explicit_item_id
    elif detected_item_id and confidence >= AUTO_READY_THRESHOLD:
        item_id = detected_item_id
    else:
        item_id = None

    return {
        "item_id": item_id,
        "detected_item_id": detected_item_id,
        "detect_confidence": confidence if detected_item_id else None,
        "analysis_summary": _summarize_upload(original_name, text, detected_item_id, confidence),
        "text_excerpt": _text_excerpt(text),
        "text_extract_error": error,
    }


def _text_excerpt(text: str) -> str | None:
    """추출 본문을 공백 정규화 후 설정 길이로 자른다. 서류 필요/해당없음 판정에 재사용."""
    compact = " ".join(str(text or "").split())
    if not compact:
        return None
    limit = settings.upload_text_excerpt_chars
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _detect_item(evidence: str, checklist: list[dict]) -> tuple[str | None, float]:
    haystack = evidence.lower()
    keyword_map = {
        "business_registration": ["사업자", "사업자등록", "business registration"],
        "corporate_seal": ["인감", "등기", "법인등기", "seal"],
        "manufacturer_letter": ["공급확약", "제조사", "확약서", "manufacturer"],
        "catalog": ["카탈로그", "catalog", "datasheet", "brochure", "기술자료"],
        "technical_compliance": ["규격대응", "규격 대응", "compliance", "사양", "spec"],
        "performance_record": ["실적", "납품실적", "performance"],
        "bid_bond": ["보증", "입찰보증", "bond"],
        "license_certificate": ["면허", "자격", "license", "certificate"],
        "bid_form": ["입찰참가신청", "입찰 참가 신청", "bid form"],
    }
    checklist_ids = {
        str(item.get("id"))
        for item in checklist
        if isinstance(item, dict) and item.get("id")
    }
    best_id: str | None = None
    best_score = 0.0
    for item_id, keywords in keyword_map.items():
        if checklist_ids and item_id not in checklist_ids:
            continue
        hits = sum(1 for kw in keywords if kw.lower() in haystack)
        if hits <= 0:
            continue
        score = min(0.95, 0.55 + hits * 0.2)
        if score > best_score:
            best_id = item_id
            best_score = score
    return best_id, best_score


def _summarize_upload(
    original_name: str,
    text: str,
    detected_item_id: str | None,
    confidence: float,
) -> str:
    normalized = " ".join(text.split())
    if normalized:
        summary = normalized[:260]
    else:
        summary = f"{original_name} 파일을 저장했습니다."
    if detected_item_id:
        summary += f" 추천 항목: {detected_item_id} ({confidence:.2f})."
    return summary


def delete_file(storage_path: str) -> bool:
    """저장된 파일 삭제. 성공/이미없음 모두 True, IO 에러는 False (라우터에서 로깅만)."""
    try:
        Path(storage_path).unlink(missing_ok=True)
        return True
    except OSError as exc:
        log.warning("[uploads] failed to delete %s: %s", storage_path, exc)
        return False


def merge_into_document_automation(
    document_automation: dict,
    uploaded: UploadedDocument,
) -> dict:
    """업로드 메타를 `document_automation.uploads`에 추가하고 매핑 항목 ready로 승격.

    item_id가 있고 해당 항목 status가 `needed`/`blocked`이면 `ready`로 자동 승격
    (수동으로 generated/not_applicable 등 다른 상태로 바꾼 경우는 존중).
    """
    updated = dict(document_automation)
    uploads = list(updated.get("uploads") or [])
    uploads.append(uploaded.model_dump())
    updated["uploads"] = uploads

    if uploaded.item_id:
        checklist = list(updated.get("checklist") or [])
        for item in checklist:
            if not isinstance(item, dict) or item.get("id") != uploaded.item_id:
                continue
            if item.get("status") in {"needed", "blocked", None}:
                item["status"] = "ready"
                source = str(item.get("source") or "rule")
                parts = [p for p in source.split("+") if p]
                if "upload" not in parts:
                    parts.append("upload")
                item["source"] = "+".join(parts)
            break
        updated["checklist"] = checklist
    return updated


def list_common_uploads() -> list[UploadedDocument]:
    path = common_metadata_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    items: list[UploadedDocument] = []
    for item in raw:
        if isinstance(item, dict):
            try:
                items.append(UploadedDocument.model_validate(item))
            except Exception:  # noqa: BLE001
                continue
    return items


def save_common_upload(uploaded: UploadedDocument) -> None:
    items = [item for item in list_common_uploads() if item.id != uploaded.id]
    items.append(uploaded)
    common_metadata_path().write_text(
        json.dumps([item.model_dump() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_common_upload(upload_id: str) -> UploadedDocument | None:
    for item in list_common_uploads():
        if item.id == upload_id:
            return item
    return None


def clone_common_upload_for_notice(uploaded: UploadedDocument) -> UploadedDocument:
    data = uploaded.model_dump()
    data["id"] = uuid.uuid4().hex
    data["source_ref"] = "common_library"
    data["uploaded_at"] = datetime.now(tz=UTC).isoformat()
    return UploadedDocument.model_validate(data)


def remove_from_document_automation(
    document_automation: dict,
    upload_id: str,
) -> tuple[dict, dict | None]:
    """uploads 배열에서 upload_id 제거. (updated_doc, removed_meta or None)."""
    updated = dict(document_automation)
    uploads = list(updated.get("uploads") or [])
    removed: dict | None = None
    survivors: list = []
    for item in uploads:
        if isinstance(item, dict) and item.get("id") == upload_id and removed is None:
            removed = item
            continue
        survivors.append(item)
    updated["uploads"] = survivors
    return updated, removed


_MIME_MAP = {
    "pdf": "application/pdf",
    "hwp": "application/x-hwp",
    "hwpx": "application/vnd.hancom.hwpx",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _guess_mime(filename: str) -> str:
    if "." not in filename:
        return "application/octet-stream"
    ext = filename.rsplit(".", 1)[-1].strip().lower()
    return _MIME_MAP.get(ext, "application/octet-stream")
