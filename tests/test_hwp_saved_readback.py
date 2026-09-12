from copy import deepcopy

import pytest

from api.workspace.hwp_readback import verify_readback
from api.workspace.hwp_validation import HwpValidationError


def report():
    fields = [{"field": "company", "occurrence": 0}, {"field": "company", "occurrence": 1}]
    return {
        "fields": ["company"], "replaced": ["company"], "missing": [],
        "remaining_placeholders": [],
        "verification": {
            "contract_version": 1, "template_sha256": "a" * 64, "output_sha256": "b" * 64,
            "template_fields": deepcopy(fields), "saved_fields": deepcopy(fields),
            "readback": [{**field, "value": "ACME\r\nKorea"} for field in fields],
            "lifecycle": ["opened", "written", "saved", "closed", "reopened", "readback", "closed", "quit"],
        },
    }


def check(raw):
    return verify_readback(raw, {"company": "ACME\nKorea"}, "a" * 64, "b" * 64)


def test_all_occurrences_and_newlines_are_verified():
    result = check(report())
    assert result["verified"] is True
    assert result["saved_occurrence_count"] == 2
    assert result["layout_review"] == "required"


def test_old_worker_without_evidence_stays_unverified():
    raw = report()
    del raw["verification"]
    assert check(raw) is None


@pytest.mark.parametrize("mutation", [
    lambda r: r["verification"].update(output_sha256="c" * 64),
    lambda r: r["verification"].update(template_sha256="c" * 64),
    lambda r: r["verification"].update(contract_version=True),
    lambda r: r["verification"]["lifecycle"].pop(),
    lambda r: r["verification"]["readback"].pop(),
    lambda r: r["verification"]["saved_fields"].pop(),
    lambda r: r["verification"]["readback"][1].update(value="Wrong company"),
    lambda r: r["verification"]["readback"][1].update(occurrence=0),
    lambda r: r["verification"]["template_fields"][1].update(occurrence=2),
    lambda r: r.update(fields=[]),
    lambda r: r.update(replaced=[]),
    lambda r: r.update(missing=["company"]),
    lambda r: r.update(remaining_placeholders=["company"]),
])
def test_inconsistent_evidence_is_failure_not_warning(mutation):
    raw = report()
    mutation(raw)
    with pytest.raises(HwpValidationError):
        check(raw)


def test_unmapped_empty_fields_must_remain_visible():
    raw = report()
    field = {"field": "unmapped", "occurrence": 0}
    raw["fields"].append("unmapped")
    raw["verification"]["template_fields"].append(field)
    raw["verification"]["saved_fields"].append(field)
    raw["verification"]["readback"].append({**field, "value": ""})
    with pytest.raises(HwpValidationError):
        check(raw)
    raw["remaining_placeholders"] = ["unmapped"]
    assert check(raw)["verified"] is True


def test_missing_requested_field_is_draft_warning_not_false_replacement():
    raw = report()
    raw["missing"] = ["absent"]
    assert verify_readback(raw, {"company": "ACME\nKorea", "absent": "value"}, "a" * 64, "b" * 64)["verified"]
