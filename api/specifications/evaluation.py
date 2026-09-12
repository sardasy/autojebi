"""Frozen, document-family split evaluation. Synthetic cases cannot open release gates."""
from __future__ import annotations

import random
import re
from collections import defaultdict
from statistics import mean

from api.workspace.service import digest

CATEGORIES = ("numeric", "interface_model", "license", "version")


def recall(expected: list[str], actual: list[str]) -> float:
    if not expected:
        raise ValueError("positive recall query must have gold evidence")
    return len(set(expected) & set(actual[:5])) / len(set(expected))


def bootstrap(values: list[dict]) -> list[float]:
    families = defaultdict(list)
    for row in values:
        families[row["family"]].append(row["final"])
    keys = sorted(families)
    rng = random.Random(20260911)
    samples = sorted(mean(score for key in rng.choices(keys, k=len(keys)) for score in families[key])
                     for _ in range(2000))
    return [samples[49], samples[1949]]


def evaluate(dataset: dict, results: dict, manifest_hash: str) -> dict:
    records = dataset["queries"]
    if len({q["id"] for q in records}) != len(records):
        raise ValueError("duplicate query id")
    split_by_family = {}
    split_by_hash = {}
    for query in records:
        if query["category"] not in CATEGORIES or query["split"] not in {"dev", "holdout", "safety"}:
            raise ValueError("invalid category/split")
        family, split = query["family"], query["split"]
        source_hash = query.get("source_sha256", "")
        if not family or not re.fullmatch(r"[a-f0-9]{64}", source_hash) or not query.get("reviewer"):
            raise ValueError("document family/source hash/reviewer required")
        if family in split_by_family and split_by_family[family] != split:
            raise ValueError("document family leaked between splits")
        split_by_family[family] = split
        if source_hash in split_by_hash and split_by_hash[source_hash] != split:
            raise ValueError("source file leaked between splits")
        split_by_hash[source_hash] = split
    scores, safety = [], []
    for query in records:
        predicted = results.get(query["id"])
        if predicted is None:
            raise ValueError("all queries require recorded predictions")
        if query["split"] == "safety":
            expected_values = query["expected_compliance"]
            if not expected_values:
                raise ValueError("safety query must contain explicit expected comparisons")
            wrong = any(actual == "meets" and expected_values.get(key) != "meets"
                        for key, actual in predicted.get("compliance", {}).items())
            safety.append({"wrong_meets": wrong,
                "passed": not wrong and all(predicted.get("compliance", {}).get(k) == expected
                    for k, expected in query["expected_compliance"].items()),
                "category": query["category"]})
        elif query["split"] == "holdout":
            scores.append({"family": query["family"], "category": query["category"],
                "final": recall(query["gold_ids"], predicted["final_ids"]),
                "raw": recall(query["gold_ids"], predicted["raw_ids"]), "gold_count": len(set(query["gold_ids"]))})
    if not scores:
        raise ValueError("no holdout predictions")
    categories = {category: {"count": len(rows), "recall_at_5": mean(r["final"] for r in rows) if rows else 0}
        for category in CATEGORIES if (rows := [r for r in scores if r["category"] == category]) is not None}
    return {"schema_version": 1, "manifest_hash": manifest_hash, "dataset_hash": digest(dataset),
        "results_hash": digest(results), "corpus_type": dataset.get("corpus_type"),
        "evaluation_version": dataset.get("version"), "dev_count": sum(q["split"] == "dev" for q in records),
        "holdout_count": len(scores), "family_count": len({r["family"] for r in scores}),
        "gold_evidence_count": sum(r["gold_count"] for r in scores), "categories": categories,
        "recall_at_5": mean(r["final"] for r in scores), "raw_recall_at_5": mean(r["raw"] for r in scores),
        "family_bootstrap_95": bootstrap(scores), "wrong_meets": sum(r["wrong_meets"] for r in safety),
        "safety_count": len(safety), "safety_passed": bool(safety) and all(r["passed"] for r in safety),
        "additional_paid_calls": results.get("_additional_paid_calls"),
        "reviewed": dataset.get("reviewed") is True}


def release_gate(report: dict, manifest_hash: str) -> bool:
    try:
        return bool(report["schema_version"] == 1 and report["manifest_hash"] == manifest_hash
            and report["corpus_type"] == "validated_real" and report["reviewed"]
            and report["evaluation_version"] and report["dataset_hash"] and report["results_hash"]
            and report["dev_count"] >= 40 and report["holdout_count"] >= 200
            and report["family_count"] >= 20 and report["recall_at_5"] >= .9
            and all(report["categories"][c]["count"] >= 50 and report["categories"][c]["recall_at_5"] >= .85 for c in CATEGORIES)
            and report["wrong_meets"] == 0 and report["safety_count"] >= 40
            and report["safety_passed"] and report["additional_paid_calls"] == 0)
    except (KeyError, TypeError):
        return False
