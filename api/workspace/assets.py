"""Company file registry with CAS edits and explicit per-notice attachment."""
from __future__ import annotations

import copy
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, update

from api.services.uploads import build_metadata, save_stream
from api.workspace import service
from api.workspace.asset_catalog import (
    AssetCategory,
    AssetCategoryCatalog,
    category_catalog,
    category_role,
)
from api.workspace.asset_policy import business_number, validity
from api.workspace.storage import source_path
from api.workspace.tables import company_asset_events, company_assets, workspaces


class AssetDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    category: AssetCategory
    subject_business_number: str = Field(default="", max_length=20)
    issued_on: date | None = None
    expires_on: date | None = None
    no_expiry: bool = False
    active: bool = True

    @field_validator("subject_business_number")
    @classmethod
    def normalize_number(cls, value: str) -> str:
        number = business_number(value)
        if number and (len(number) != 10 or not number.isascii() or not number.isdigit()):
            raise ValueError("사업자번호는 숫자 10자리로 입력하세요.")
        return number

    @model_validator(mode="after")
    def check_dates(self) -> AssetDetails:
        if self.no_expiry and self.expires_on:
            raise ValueError("유효기간과 만료 없음 중 하나만 선택하세요.")
        if self.issued_on and self.expires_on and self.issued_on > self.expires_on:
            raise ValueError("만료일이 발급일보다 빠릅니다.")
        return self


class AssetEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    details: AssetDetails
    note: str = Field(min_length=1, max_length=2000)


class AssetLink(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    asset_version: int = Field(ge=1)


class AssetRecord(BaseModel):
    id: str
    version: int
    details: AssetDetails
    file: dict[str, Any]
    validity: str
    role: str
    created_at: datetime
    updated_at: datetime


class AssetList(BaseModel):
    category_catalog: AssetCategoryCatalog = Field(default_factory=category_catalog)
    items: list[AssetRecord]
    page: int
    has_more: bool
    alerts: dict[str, int]


def role(details: dict) -> str:
    return category_role(details["category"])


def public(row: dict) -> AssetRecord:
    file = {key: row["file"].get(key) for key in ("id", "name", "sha256", "size", "mime")}
    return AssetRecord(**{**row, "file":file, "role":role(row["details"]),
                          "validity":validity(row["details"])})


def load(conn: Any, asset_id: str, version: int | None = None) -> dict:
    row = conn.execute(select(company_assets).where(company_assets.c.id == asset_id)
                       .with_for_update()).mappings().first()
    if not row:
        service.fail("asset_missing", "중앙 자료를 찾을 수 없습니다.", status=404)
    if version is not None and row["version"] != version:
        service.fail("asset_version_conflict", "중앙 자료가 변경되었습니다. 목록을 새로고침하세요.")
    return dict(row)


def create(conn: Any, stream: BinaryIO, name: str, mime: str | None, details: AssetDetails) -> dict:
    # This registry never runs COM or an LLM while accepting a file.
    from api.parsing.attachment_text import checked_archive
    from api.parsing.hwp_validation import validate_hwp_content

    if Path(name).suffix.lower() not in {".pdf", ".hwp", ".hwpx", ".xlsx"}:
        service.fail("asset_format", "중앙 자료는 PDF, HWP, HWPX, XLSX 원본을 등록하세요.", status=415)
    saved = save_stream(stream, notice_no="company-assets", original_name=name)
    file = build_metadata(saved, original_name=name, mime=mime, item_id=None).model_dump()
    path = source_path(file)
    try:
        data = path.read_bytes()
        ext = path.suffix.lower()
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                if not pdf.pages:
                    raise ValueError("empty PDF")
        elif ext in {".hwp", ".hwpx"}:
            validate_hwp_content(data, ext)
        else:
            with checked_archive(data) as archive:
                if "xl/workbook.xml" not in archive.namelist():
                    raise ValueError("not XLSX")
    except Exception:
        path.unlink(missing_ok=True)
        service.fail("asset_format", "확장자와 파일 형식을 확인할 수 없습니다.", "정상적으로 열리는 원본을 등록하세요.", status=415)
    row = dict(id=service.uid(), version=1, details=details.model_dump(mode="json"), file=file,
               created_at=service.now(), updated_at=service.now())
    conn.execute(company_assets.insert().values(**row))
    conn.execute(company_asset_events.insert().values(id=service.uid(), asset_id=row["id"],
        version=1, details=row["details"], note="원본 등록; 공고별 증빙 승인은 별도", created_at=service.now()))
    return row


def edit(conn: Any, asset_id: str, body: AssetEdit) -> dict:
    row = load(conn, asset_id, body.version)
    details = body.details.model_dump(mode="json")
    if details == row["details"]:
        return row
    # Do not relabel old proposals as evidence, even before they are attached.
    if role(details) != role(row["details"]):
        service.fail("asset_role_immutable", "자료 구분을 바꾸려면 별도 원본으로 등록하세요.", status=422)
    count = conn.execute(update(company_assets).where(company_assets.c.id == asset_id,
        company_assets.c.version == body.version).values(details=details,
        version=body.version + 1, updated_at=service.now())).rowcount
    if count != 1:
        service.fail("asset_version_conflict", "중앙 자료가 변경되었습니다.")
    conn.execute(company_asset_events.insert().values(id=service.uid(), asset_id=asset_id,
        version=body.version + 1, details=details, note=body.note, created_at=service.now()))
    # Keep linked files/snapshots and review history, but invalidate their current approval.
    for ws in conn.execute(select(workspaces).order_by(workspaces.c.notice_no)
                           .with_for_update()).mappings().all():
        inputs = copy.deepcopy(ws["inputs"])
        affected = False
        for doc in inputs.get("documents", []):
            if (doc.get("company_asset") or {}).get("id") == asset_id:
                doc["company_asset"]["stale"] = True
                doc["confirmed"] = False
                affected = True
        if affected:
            service.change(conn, dict(ws), inputs, "asset_changed", "중앙 자료 변경: 재연결·검토 필요")
    return load(conn, asset_id)


def link(conn: Any, notice_no: str, asset_id: str, body: AssetLink) -> None:
    row = load(conn, asset_id, body.asset_version)
    ws = service.load(conn, notice_no, body.version)
    if not row["details"]["active"]:
        service.fail("asset_disabled", "비활성 자료는 새로 연결할 수 없습니다.")
    source_path(row["file"])
    inputs = copy.deepcopy(ws["inputs"])
    existing = next((d for d in inputs["documents"]
                     if (d.get("company_asset") or {}).get("id") == asset_id), None)
    if existing and existing["company_asset"]["version"] == row["version"] and not existing["company_asset"].get("stale"):
        return
    doc = existing or {**row["file"], "id":service.uid(), "text":"", "text_origin":"unread"}
    doc.update(role=role(row["details"]), confirmed=False,
               company_asset={"id":asset_id, "version":row["version"], **row["details"], "stale":False})
    if not existing:
        inputs["documents"].append(doc)
    service.change(conn, ws, inputs, "asset_link", "중앙 자료 연결; 회사·기간·본문 확인 전 미승인")
