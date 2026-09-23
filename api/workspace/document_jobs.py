"""Version-aware document job identity, serialized on the workspace row."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select

from api.parsing.document_comparison import COMPARISON_VERSION
from api.parsing.hwpx_text import TEXT_RULE_VERSION
from api.services.document_reference import REFERENCE_ENGINE_VERSION
from api.services.kordoc_client import enabled
from api.workspace.errors import fail
from api.workspace.tables import workspaces


def parameters(conn: Any, notice_no: str, body: Any) -> dict:
    params = {"template_key": body.template_key, "visible": body.visible}
    if body.kind not in {"extract", "document_compare"}:
        return params
    if body.kind == "document_compare" and not enabled():
        fail("kordoc_disabled", "문서 추출 비교 설정을 활성화하세요.", status=503)
    ws = conn.execute(select(workspaces).where(workspaces.c.notice_no == notice_no)
                      .with_for_update()).mappings().first()
    if not ws:
        return params
    identity = {"notice_no": notice_no, "input_version": body.input_version,
                "text_rule_version": TEXT_RULE_VERSION,
                "comparison_version": COMPARISON_VERSION if body.kind == "document_compare" else None,
                "reference_version": REFERENCE_ENGINE_VERSION if body.kind == "document_compare" else None,
                "documents": [{"id": d["id"], "sha256": d.get("sha256"),
                               "text_sha256": hashlib.sha256((d.get("text") or "").encode()).hexdigest()}
                              for d in ws["inputs"]["documents"]]}
    params["document_rules"] = identity
    params["document_identity"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return params


def reusable(kind: str, old: dict, current: dict) -> bool:
    return kind not in {"extract", "document_compare"} or old.get("document_identity") == current.get("document_identity")
