import copy
import hashlib

import pytest

from api.specifications.evaluation import CATEGORIES, evaluate, release_gate


def dataset():
    data = {"version": "SYNTHETIC-v1", "corpus_type": "synthetic", "reviewed": True, "queries": []}
    results = {"_additional_paid_calls": 0}
    for category in CATEGORIES:
        for split, count in (("dev", 10), ("holdout", 50), ("safety", 10)):
            for index in range(count):
                key = f"{category}-{split}-{index}"
                data["queries"].append({"id": key, "family": f"{category}-{split}-{index // 2}", "split": split,
                    "source_sha256": hashlib.sha256(key.encode()).hexdigest(), "reviewer": "synthetic test", "category": category,
                    "gold_ids": [key], "expected_compliance": {key: "unassessed"}})
                results[key] = {"final_ids": [key], "raw_ids": [key], "compliance": {key: "unassessed"}}
    return data, results


def test_synthetic_240_retrieval_cases_are_not_release_evidence():
    data, results = dataset()
    report = evaluate(data, results, "manifest")
    assert report["holdout_count"] == 200 and report["dev_count"] == 40
    assert report["recall_at_5"] == 1
    assert report["family_bootstrap_95"] == [1, 1]
    assert not release_gate(report, "manifest")


def test_split_leakage_is_rejected():
    data, results = dataset()
    data["queries"][10]["family"] = data["queries"][0]["family"]
    with pytest.raises(ValueError, match="leaked"):
        evaluate(data, results, "manifest")


def test_wrong_meets_and_missing_paid_call_measurement_block_release():
    data, results = dataset()
    key = next(q["id"] for q in data["queries"] if q["split"] == "safety")
    results[key]["compliance"][key] = "meets"
    report = evaluate(data, results, "manifest")
    assert report["wrong_meets"] == 1 and not report["safety_passed"]
    report["corpus_type"] = "validated_real"
    assert not release_gate(report, "manifest")


def test_category_regression_and_manifest_mismatch_rejected():
    data, results = dataset()
    report = evaluate(data, results, "manifest")
    report["corpus_type"] = "validated_real"  # Gate contract only, not a real benchmark.
    assert release_gate(report, "manifest")
    assert not release_gate(report, "other-model")
    degraded = copy.deepcopy(report)
    degraded["categories"]["license"]["recall_at_5"] = .8
    assert not release_gate(degraded, "manifest")


def test_relabelled_document_family_cannot_hide_source_leakage():
    data, results = dataset()
    data["queries"][10]["source_sha256"] = data["queries"][0]["source_sha256"]
    with pytest.raises(ValueError, match="source file leaked"):
        evaluate(data, results, "manifest")


def test_unlabelled_positive_safety_prediction_blocks_release():
    data, results = dataset()
    key = next(q["id"] for q in data["queries"] if q["split"] == "safety")
    results[key]["compliance"]["unexpected-evidence"] = "meets"
    report = evaluate(data, results, "manifest")
    assert report["wrong_meets"] == 1 and not report["safety_passed"]
