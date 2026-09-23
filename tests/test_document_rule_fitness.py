import hashlib
import json
from pathlib import Path

import pytest

from api.parsing.attachment_text import extract_hwpx
from api.parsing.document_comparison import COMPARISON_VERSION, compare_document
from api.parsing.hwpx_text import TEXT_RULE_VERSION
from api.parsing.text_diff import diff_text
from tests.document_comparison_samples import reference, sample
from tools.check_document_rule_manifest import check_immutable


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def rule_hashes() -> dict:
    raw = sample()
    old, new = extract_hwpx(raw, rule_version=1), extract_hwpx(raw)
    return {"extraction": {"1": digest(old["text"]), str(TEXT_RULE_VERSION): digest(new)},
            "comparison": {str(COMPARISON_VERSION): digest([
                compare_document(raw, ".hwpx", old["text"], reference()),
                compare_document(raw, ".hwpx", new["text"], reference("😀 Clickhere 9 본문\n230 V", "230 V")),
                diff_text("200 이상\nA\nB", "220 이하\nB\nA"),
            ])}}


def test_rule_fixture_hashes_require_version_bump():
    recorded = json.loads(Path("tests/fixtures/document_rule_hashes.json").read_text(encoding="utf-8"))
    for rule, versions in rule_hashes().items():
        for version, value in versions.items():
            assert recorded[rule][version] == value, f"Bump {rule} version; never overwrite a published hash"


def test_existing_rule_hash_cannot_be_replaced_or_removed():
    old = {"extraction": {"1": "old"}}
    with pytest.raises(ValueError):
        check_immutable(old, {"extraction": {"1": "changed"}})
    with pytest.raises(ValueError):
        check_immutable(old, {"extraction": {"2": "new"}})
    check_immutable(old, {"extraction": {"1": "old", "2": "new"}})
