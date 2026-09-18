from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.specifications.models import Specification
from api.specifications.validation import compare, parse_numeric, scale, sha, validate_spec


def spec(raw="장치 지연 1ms 이하", **kwargs):
    doc = {"id": "source", "sha256": "a" * 64, "text": raw, "role": "notice_source"}
    value = Specification(target="장치", property="latency", kind="numeric", operator="le",
        value="1", unit="ms", raw=raw, source={"document_id": "source", "document_sha256": doc["sha256"],
            "text_sha256": sha(raw), "start": 0, "end": len(raw), "quote": raw, "locator": "page 1"})
    if kwargs:
        value = Specification.model_validate({**value.model_dump(), **kwargs})
    return value, doc


@pytest.mark.parametrize("value,unit,expected", [
    ("999.97", "μs", "meets"), ("1000", "µs", "meets"), ("1000.01", "us", "does_not_meet"),
    ("1.000000000000000000000000000001", "ms", "does_not_meet"),
    (".999999999999999999999999999999", "ms", "meets"),
])
def test_exact_boundary_no_relative_tolerance(value, unit, expected):
    requirement, _ = spec()
    evidence = requirement.model_copy(update={"operator": "eq", "value": value, "unit": unit})
    assert compare(requirement, evidence) == expected


@pytest.mark.parametrize("operator,value,spread,expected", [
    ("lt", "1", "0", "does_not_meet"), ("gt", "1", "0", "does_not_meet"),
    ("le", "1", ".01", "unassessed"), ("le", ".9", ".01", "meets"),
    ("le", "1.1", ".01", "does_not_meet"), ("eq", "1", ".01", "unassessed"),
])
def test_uncertainty_and_open_boundaries(operator, value, spread, expected):
    req, _ = spec(operator=operator)
    ev = req.model_copy(update={"operator": "eq", "value": value, "uncertainty": spread})
    assert compare(req, ev) == expected


def test_range_edge_and_compatible_units():
    req, _ = spec(operator="range", value=None, lower=".9", upper="1", upper_inclusive=False)
    assert compare(req, req.model_copy(update={"operator": "eq", "value": "1000", "unit": "us"})) == "does_not_meet"
    assert scale("1", "ms") == Decimal(".001")


@pytest.mark.parametrize("changes", [{"property": "time_step"}, {"target": "다른 장치"},
    {"unit": "Hz"}, {"conditions": "조건부"}, {"operator": "unknown"}])
def test_no_inference_across_properties_targets_or_conditions(changes):
    req, _ = spec()
    ev = req.model_copy(update={"operator": "eq", **changes})
    assert compare(req, ev) == "unassessed"


def test_full_validation_source_and_shacl():
    req, doc = spec()
    assert validate_spec(req, doc)["status"] == "valid"
    assert validate_spec(req.model_copy(update={"value": "2"}), doc)["codes"] == ["dual_parse_mismatch"]
    assert "source_changed" in validate_spec(req, {**doc, "text": doc["text"] + "!"})["codes"]
    assert "target_unverified" in validate_spec(req.model_copy(update={"target": "다른 장치"}), doc)["codes"]


def test_double_negation_and_ambiguous_scope():
    raw = "장치 해상도 10비트 미만이 아님"
    req, doc = spec(raw, property="resolution", unit="비트", value="10", operator="ge")
    result = validate_spec(req, doc)
    assert result["status"] == "valid"
    assert result["expression"] == "NOT(LT(10))"
    assert parse_numeric("장치 해상도 10비트 미만이 아닌 경우 제외")["code"] == "condition_requires_review"


def test_range_and_uncertainty_source_validation():
    req, doc = spec("장치 지연 0.9ms 초과 1ms 이하", operator="range", value=None,
                    lower=".9", upper="1", lower_inclusive=False)
    assert validate_spec(req, doc)["status"] == "valid"
    req, doc = spec("장치 지연 1ms ± 0.01ms", operator="eq", uncertainty=".01")
    assert validate_spec(req, doc)["status"] == "valid"
    assert "dual_parse_mismatch" in validate_spec(req.model_copy(update={"uncertainty": ".02"}), doc)["codes"]


def test_protocol_and_version_never_numeric():
    req, doc = spec("장치 프로토콜 CAN 2.0B", property="protocol", kind="identifier", operator="eq", value=None, unit="", identifier="CAN 2.0B")
    assert validate_spec(req, doc)["status"] == "valid"
    assert compare(req, req.model_copy(update={"identifier": "CAN 2.0A"})) == "does_not_meet"
    assert "identifier_unverified" in validate_spec(req.model_copy(update={"identifier": "CAN 2"}), doc)["codes"]


def test_requirement_tolerance_is_distinct_from_measurement_uncertainty():
    req, doc = spec("장치 지연 1ms 허용오차 ± 0.01ms", operator="eq", tolerance=".01")
    assert validate_spec(req, doc)["status"] == "valid"
    ev = req.model_copy(update={"tolerance": None, "value": "1.009", "uncertainty": ".002"})
    assert compare(req, ev) == "unassessed"
    assert compare(req, ev.model_copy(update={"value": "1.008"})) == "meets"
    assert compare(req, ev.model_copy(update={"value": "1.02"})) == "does_not_meet"
    uncertain_req, _ = spec("장치 지연 1ms ± 0.01ms", operator="eq", uncertainty=".01")
    assert compare(uncertain_req, ev) == "unassessed"
    assert "dual_parse_mismatch" in validate_spec(req.model_copy(update={"tolerance": ".1"}), doc)["codes"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "bad", "1e999"])
def test_invalid_numbers_are_validation_errors(value):
    with pytest.raises(ValidationError):
        spec(value=value)


def test_validator_absence_is_not_success(monkeypatch):
    from api.specifications import validation
    def missing(_):
        raise ImportError
    monkeypatch.setattr(validation, "rdf_check", missing)
    req, doc = spec()
    assert validate_spec(req, doc)["codes"] == ["validator_unavailable"]


@pytest.mark.parametrize("raw", ["장치 전압 > 5 V", "장치 전압 >= 5 V", "장치 전압 1,000 V", "장치가 지원하지 않는 전압 5 V"])
def test_partial_numeric_and_prefix_operator_never_equality(raw):
    assert "code" in parse_numeric(raw)


@pytest.mark.parametrize("raw", ["Device does not support CAN2.0B", "Device CAN2.0B 미지원"])
def test_negative_identifier_never_meets(raw):
    req, doc = spec(raw, target="Device", property="protocol", kind="identifier", operator="eq",
                    value=None, unit="", identifier="CAN2.0B")
    assert "identifier_condition_ambiguous" in validate_spec(req, doc)["codes"]
