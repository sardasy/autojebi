"""Pilot protocol must be fixed before observation; missing data is not success."""

import copy
import json
from datetime import UTC, datetime

import pytest

from tools.company_pilot import CASES, STAGES, freeze, initialize, lock_validation, report


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def measurement(key, seconds=100, *, improved=False):
    return {"case_id": key, "operator": "synthetic-reviewer", "started_at": "2026-09-22T10:00:00+00:00" if improved else "2026-09-20T10:00:00+00:00",
            "completed_at": "2026-09-22T12:00:00+00:00" if improved else "2026-09-20T12:00:00+00:00",
            "stages": {s: {"active_seconds": seconds, "wait_seconds": 0} for s in STAGES},
            "draft_seconds": 100, "correction_seconds": 20, "mandatory_fields": 10,
            "populated_fields": 8, "corrected_fields": 1, "refinds": 0, "post_pass_omissions": 0, "unsafe_passes": 0,
            "correction_reasons": {"missing_evidence": 1, "extraction": 0, "layout": 0, "judgment": 0},
            "source_hashes": ["a" * 64], "limitations": ["synthetic fixture only"],
            "confirmation_required_fields": 2, "readiness_reason_counts": {"evidence_unconfirmed": 2},
            "code_revision": "test-code", "rule_version": "test-rules"}


@pytest.fixture
def pilot(tmp_path):
    initialize(tmp_path)
    draft = json.loads((tmp_path / "pilot.json").read_text(encoding="utf-8"))
    draft.update(confirmed_by="synthetic-owner", targets_confirmed=True, code_revision="before-A", rule_version="before-A")
    draft["staff"] = {k: {"name": "synthetic-person", "hours_per_week": 4} for k in draft["staff"]}
    draft["baseline"] = [measurement(key) for key in CASES]
    for case, attribute in zip(draft["cases"], ("goods", "software", "technical_evaluation", "complex_qualification", "correction"), strict=True):
        case.update(notice_no="SYNTHETIC-" + case["case_id"], attributes=[attribute], source_hashes=["a" * 64],
                    required_company_materials=["synthetic certificate"], independent_reference="fixture checklist",
                    draft_sample=case["case_id"] in {"A", "B"})
    save(tmp_path / "pilot.json", draft)
    frozen = freeze(tmp_path, at=datetime(2026, 9, 21, tzinfo=UTC))
    a = measurement("A", 70, improved=True)
    a.update(started_at="2026-09-21T01:00:00Z", completed_at="2026-09-21T02:00:00Z")
    improved = {"protocol_sha256": frozen["sha256"], "code_revision": "test-code", "rule_version": "test-rules",
                "registry_setup_seconds": 500, "runs": [a]}
    save(tmp_path / "improved.json", improved)
    lock_validation(tmp_path, at=datetime(2026, 9, 21, 3, tzinfo=UTC))
    return tmp_path, improved


def test_init_is_unmeasured_and_never_overwrites(tmp_path):
    initialize(tmp_path)
    with pytest.raises(ValueError):
        freeze(tmp_path)
    assert not (tmp_path / "protocol-frozen.json").exists()
    with pytest.raises(ValueError):
        initialize(tmp_path)


def test_five_case_value_report_keeps_development_separate(pilot):
    folder, improved = pilot
    improved["runs"].extend(measurement(key, 70, improved=True) for key in CASES[1:])
    save(folder / "improved.json", improved)
    result = report(folder)
    assert result["status"] == "targets_met" and result["completed_cases"] == 5
    assert result["median_time_reduction"] == pytest.approx(0.3)
    assert result["validation_median_time_reduction"] == pytest.approx(0.3)
    assert result["cases"][0]["cohort"] == "development"
    assert result["registry_setup_seconds"] == 500
    assert result["observed_savings_seconds"] == 600
    assert result["cases"][0]["confirmation_required_fraction"] == pytest.approx(0.2)
    assert result["cases"][0]["readiness_reason_counts"] == {"evidence_unconfirmed": 2}


def test_missing_cases_and_setup_are_incomplete(pilot):
    folder, improved = pilot
    assert report(folder)["status"] == "incomplete"
    improved["runs"].extend(measurement(key, 70, improved=True) for key in CASES[1:])
    improved["registry_setup_seconds"] = None
    save(folder / "improved.json", improved)
    assert report(folder)["status"] == "incomplete"


def test_three_slower_cases_stop_investment(pilot):
    folder, improved = pilot
    improved["runs"].extend(measurement(key, 120, improved=True) for key in ("B", "C", "D"))
    save(folder / "improved.json", improved)
    assert report(folder)["status"] == "hold_value"


def test_safety_failure_overrides_time_savings(pilot):
    folder, improved = pilot
    row = measurement("B", 1, improved=True)
    row["post_pass_omissions"] = 1
    improved["runs"].append(row)
    save(folder / "improved.json", improved)
    assert report(folder)["status"] == "hold_safety"


def test_unmeasured_confirmation_fields_are_not_treated_as_zero(pilot):
    folder, improved = pilot
    for key in CASES[1:]:
        row = measurement(key, 70, improved=True)
        row.update(confirmation_required_fields=None, readiness_reason_counts=None)
        improved["runs"].append(row)
    save(folder / "improved.json", improved)
    result = report(folder)
    assert result["status"] == "incomplete"
    assert result["cases"][1]["confirmation_required_fraction"] is None


@pytest.mark.parametrize("counts", [{"invented_reason": 2}, {"evidence_unconfirmed": 1}, {"evidence_unconfirmed": -1}])
def test_pending_reason_counts_must_have_valid_codes_and_fixed_denominator(pilot, counts):
    folder, improved = pilot
    row = measurement("B", 70, improved=True)
    row["readiness_reason_counts"] = counts
    improved["runs"].append(row)
    save(folder / "improved.json", improved)
    with pytest.raises(ValueError):
        report(folder)


@pytest.mark.parametrize("change", ["hash", "denominator", "duplicate", "prefreeze", "version", "rewrite_A"])
def test_invalid_comparisons_are_rejected(pilot, change):
    folder, improved = pilot
    row = measurement("B", 70, improved=True)
    if change == "hash":
        row["source_hashes"] = ["b" * 64]
    elif change == "denominator":
        row["mandatory_fields"] = 11
    elif change == "duplicate":
        improved["runs"].append(copy.deepcopy(row))
    elif change == "prefreeze":
        row["started_at"] = "2026-09-20T10:00:00Z"
    elif change == "version":
        row["rule_version"] = "different-rule"
    else:
        improved["runs"][0]["refinds"] = 1
    improved["runs"].append(row)
    save(folder / "improved.json", improved)
    with pytest.raises(ValueError):
        report(folder)


def test_frozen_targets_cannot_be_overwritten_or_edited(pilot):
    folder, _ = pilot
    with pytest.raises(ValueError, match="개선 결과"):
        freeze(folder)
    frozen = json.loads((folder / "protocol-frozen.json").read_text(encoding="utf-8"))
    frozen["protocol"]["targets"]["median_time_reduction"] = 0
    save(folder / "protocol-frozen.json", frozen)
    with pytest.raises(ValueError, match="해시"):
        report(folder)
