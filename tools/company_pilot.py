"""Initialize, freeze and report the five-case practitioner pilot; never approves bids.

Run as ``python -m tools.company_pilot init data/company-pilot``. All measurements
are human-entered observations. A hash detects edits, not the truth of a timing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from api.workspace.readiness_issues import IssueCode

STAGES = ("conditions", "requirements", "evidence_search", "final_review")
CASES = ("A", "B", "C", "D", "E")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Timing(StrictModel):
    active_seconds: float = Field(ge=0)
    wait_seconds: float = Field(ge=0)


class Measurement(StrictModel):
    case_id: Literal["A", "B", "C", "D", "E"]
    operator: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    stages: dict[str, Timing]
    draft_seconds: float | None = Field(default=None, ge=0)
    correction_seconds: float | None = Field(default=None, ge=0)
    mandatory_fields: int = Field(gt=0)
    populated_fields: int = Field(ge=0)
    corrected_fields: int = Field(ge=0)
    refinds: int = Field(ge=0)
    post_pass_omissions: int = Field(ge=0)
    unsafe_passes: int = Field(ge=0)
    correction_reasons: dict[Literal["missing_evidence", "extraction", "layout", "judgment"], int]
    source_hashes: list[str] = Field(min_length=1)
    limitations: list[str]
    confirmation_required_fields: int | None = Field(default=None, ge=0)
    readiness_reason_counts: dict[IssueCode, int] | None = None
    code_revision: str = ""
    rule_version: str = ""

    @field_validator("source_hashes")
    @classmethod
    def hashes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(
            len(item) != 64 or any(c not in "0123456789abcdef" for c in item) for item in value
        ):
            raise ValueError("원본 해시는 중복 없는 소문자 SHA-256 목록이어야 합니다.")
        return value

    @model_validator(mode="after")
    def consistency(self) -> Measurement:
        if set(self.stages) != set(STAGES):
            raise ValueError("공통 측정 단계 4개를 모두 기록하세요.")
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("측정 시각에 시간대가 필요합니다.")
        if self.completed_at <= self.started_at:
            raise ValueError("측정 종료는 시작 이후여야 합니다.")
        if not self.operator.strip() or any(v < 0 for v in self.correction_reasons.values()):
            raise ValueError("실제 처리자와 음수가 아닌 수정 건수가 필요합니다.")
        if set(self.correction_reasons) != {"missing_evidence", "extraction", "layout", "judgment"}:
            raise ValueError("네 가지 수정 사유를 모두 기록하세요.")
        if max(self.populated_fields, self.corrected_fields) > self.mandatory_fields:
            raise ValueError("필수 항목 분모보다 큰 항목 수입니다.")
        if sum(self.correction_reasons.values()) != self.corrected_fields:
            raise ValueError("수정 항목별 주된 사유를 한 개씩 분류하세요.")
        if self.confirmation_required_fields is not None:
            if self.confirmation_required_fields > self.mandatory_fields:
                raise ValueError("확인 필요 항목 수가 필수 항목 분모보다 큽니다.")
            if self.readiness_reason_counts is None or any(v < 0 for v in self.readiness_reason_counts.values()):
                raise ValueError("확인 필요 항목의 사유 코드별 건수를 기록하세요.")
            if sum(self.readiness_reason_counts.values()) != self.confirmation_required_fields:
                raise ValueError("확인 필요 항목마다 주된 사유 코드 한 개를 기록하세요.")
        elif self.readiness_reason_counts is not None:
            raise ValueError("사유별 건수와 함께 확인 필요 항목 수도 기록하세요.")
        return self


class Case(StrictModel):
    case_id: Literal["A", "B", "C", "D", "E"]
    notice_no: str = Field(min_length=1)
    attributes: list[Literal["goods", "software", "technical_evaluation", "complex_qualification", "correction"]] = Field(min_length=1)
    deadline_state: Literal["open", "closed", "unknown"]
    source_hashes: list[str] = Field(min_length=1)
    required_company_materials: list[str] = Field(min_length=1)
    draft_sample: bool
    independent_reference: str = Field(min_length=1)


class Targets(StrictModel):
    median_time_reduction: float = Field(ge=0, le=1)
    max_draft_correction_ratio: float = Field(ge=0)
    stop_if_slower_cases: int = Field(ge=1, le=5)
    max_refinds: int = Field(ge=0)


class ProtocolDraft(StrictModel):
    version: str = Field(min_length=1)
    confirmed_by: str = Field(min_length=1)
    targets_confirmed: Literal[True]
    code_revision: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    staff: dict[str, dict[str, Any]]
    cases: list[Case]
    baseline: list[Measurement]
    targets: Targets

    @model_validator(mode="after")
    def complete(self) -> ProtocolDraft:
        if len(self.cases) != 5 or {c.case_id for c in self.cases} != set(CASES):
            raise ValueError("A~E 공고 5건을 중복 없이 선정하세요.")
        if len({c.notice_no.strip() for c in self.cases}) != 5:
            raise ValueError("서로 다른 공고 5건이 필요합니다.")
        if {tag for case in self.cases for tag in case.attributes} != {
            "goods", "software", "technical_evaluation", "complex_qualification", "correction"
        }:
            raise ValueError("물품·소프트웨어·기술평가·복합 자격·정정공고 속성을 포함하세요.")
        if len(self.baseline) != 5 or {m.case_id for m in self.baseline} != set(CASES):
            raise ValueError("5건의 기준선을 모두 측정하세요.")
        if sum(c.draft_sample for c in self.cases) != 2:
            raise ValueError("초안 측정 대상은 사전 선정한 2건이어야 합니다.")
        for role in ("developer", "practitioner", "evaluation_owner"):
            person = self.staff.get(role, {})
            hours = person.get("hours_per_week")
            if not str(person.get("name") or "").strip() or not isinstance(hours, int | float) or not 0 < hours <= 168:
                raise ValueError(f"{role}: 실제 담당자와 주당 가용 시간을 기록하세요.")
        for case in self.cases:
            baseline = next(m for m in self.baseline if m.case_id == case.case_id)
            if set(case.source_hashes) != set(baseline.source_hashes):
                raise ValueError("선정표와 기준선 원본 해시가 다릅니다.")
            if sum(t.active_seconds for t in baseline.stages.values()) <= 0:
                raise ValueError("활동 시간이 0인 기준선은 절감률을 측정할 수 없습니다.")
            if baseline.confirmation_required_fields is None:
                raise ValueError("기준선의 확인 필요 항목 수와 사유를 측정한 뒤 목표를 고정하세요.")
            if case.draft_sample and (baseline.draft_seconds is None or baseline.correction_seconds is None):
                raise ValueError("초안 대상 2건의 작성·수정 시간을 기록하세요.")
        return self


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def initialize(folder: Path) -> None:
    if folder.exists() and any(folder.iterdir()):
        raise ValueError("비어 있는 새 측정 폴더를 지정하세요. 기존 측정은 덮어쓰지 않습니다.")
    folder.mkdir(parents=True, exist_ok=True)
    draft = {"version": "evaluation-protocol-v1", "confirmed_by": "", "targets_confirmed": False,
             "code_revision": "", "rule_version": "", "staff": {
                 role: {"name": "", "hours_per_week": None}
                 for role in ("developer", "practitioner", "evaluation_owner")},
             "cases": [{"case_id": key, "notice_no": "", "attributes": [], "deadline_state": "unknown",
                        "source_hashes": [], "required_company_materials": [], "draft_sample": False,
                        "independent_reference": ""} for key in CASES], "baseline": [],
             "targets": {"median_time_reduction": 0.15, "max_draft_correction_ratio": 1.0,
                         "stop_if_slower_cases": 3, "max_refinds": 0}}
    measurement = {"case_id": "A", "operator": "", "started_at": None, "completed_at": None,
                   "stages": {stage: {"active_seconds": None, "wait_seconds": None} for stage in STAGES},
                   "draft_seconds": None, "correction_seconds": None, "mandatory_fields": None,
                   "populated_fields": None, "corrected_fields": None, "refinds": None,
                   "post_pass_omissions": None, "unsafe_passes": None,
                   "correction_reasons": {key: 0 for key in ("missing_evidence", "extraction", "layout", "judgment")},
                   "source_hashes": [], "limitations": []}
    measurement.update(confirmation_required_fields=None, readiness_reason_counts=None)
    write_new(folder / "pilot.json", draft)
    write_new(folder / "measurement-template.json", measurement)
    write_new(folder / "improved.json", {"protocol_sha256": "", "code_revision": "", "rule_version": "",
                                         "registry_setup_seconds": None, "runs": []})


def freeze(folder: Path, *, at: datetime | None = None) -> dict:
    at = at or datetime.now(UTC)
    raw = json.loads((folder / "pilot.json").read_text(encoding="utf-8"))
    protocol = ProtocolDraft.model_validate(raw)
    improved = json.loads((folder / "improved.json").read_text(encoding="utf-8"))
    if improved.get("runs"):
        raise ValueError("개선 결과가 이미 있습니다. 결과를 본 뒤 목표를 고정할 수 없습니다.")
    if any(m.completed_at >= at for m in protocol.baseline):
        raise ValueError("기준선 측정을 완료한 뒤 목표를 고정하세요.")
    payload = {"frozen_at": at.isoformat(), "protocol": protocol.model_dump(mode="json")}
    payload["sha256"] = digest(payload)
    write_new(folder / "protocol-frozen.json", payload)
    return payload


def report(folder: Path) -> dict:
    frozen = json.loads((folder / "protocol-frozen.json").read_text(encoding="utf-8"))
    expected = frozen.pop("sha256")
    if digest(frozen) != expected:
        raise ValueError("고정된 평가 규칙의 해시가 달라졌습니다.")
    protocol = ProtocolDraft.model_validate(frozen["protocol"])
    improved = json.loads((folder / "improved.json").read_text(encoding="utf-8"))
    if improved["protocol_sha256"] != expected:
        raise ValueError("측정 결과를 고정된 평가 규칙 해시에 연결하세요.")
    rows = [Measurement.model_validate(row) for row in improved["runs"]]
    if len({row.case_id for row in rows}) != len(rows):
        raise ValueError("동일 공고의 재실행으로 최초 결과를 덮어쓰지 마세요.")
    release_path = folder / "validation-release.json"
    release = json.loads(release_path.read_text(encoding="utf-8")) if release_path.exists() else None
    if release:
        release_hash = release.pop("sha256")
        if digest(release) != release_hash or release["protocol_sha256"] != expected:
            raise ValueError("검증 코드/규칙 고정 기록이 변경되었습니다.")
        a_rows = [r.model_dump(mode="json") for r in rows if r.case_id == "A"]
        if digest(a_rows) != release["development_run_sha256"]:
            raise ValueError("개발용 A의 최초 관찰 결과가 바뀌었습니다.")
    results = []
    correction_pairs = []
    for row in rows:
        base = next(m for m in protocol.baseline if m.case_id == row.case_id)
        case = next(c for c in protocol.cases if c.case_id == row.case_id)
        if row.started_at < datetime.fromisoformat(frozen["frozen_at"]):
            raise ValueError("개선 실행 전에 평가 규칙을 고정해야 합니다.")
        if not row.code_revision.strip() or not row.rule_version.strip():
            raise ValueError("실제 실행한 코드와 규칙 버전을 각 측정에 기록하세요.")
        if row.case_id != "A" and (not release or row.started_at < datetime.fromisoformat(release["locked_at"])
                                  or (row.code_revision, row.rule_version) != (release["code_revision"], release["rule_version"])):
            raise ValueError("A 점검 후 검증 버전을 고정하고 B~E를 동일 버전으로 실행하세요.")
        if set(row.source_hashes) != set(base.source_hashes) or row.mandatory_fields != base.mandatory_fields:
            raise ValueError("동일한 원본 집합과 필수 항목 분모로 비교하세요.")
        before = sum(t.active_seconds for t in base.stages.values())
        after = sum(t.active_seconds for t in row.stages.values())
        if case.draft_sample and row.correction_seconds is not None and row.draft_seconds is not None:
            correction_pairs.append((base.correction_seconds, row.correction_seconds))
        results.append({"case_id": row.case_id, "cohort": "development" if row.case_id == "A" else "validation",
                        "baseline_seconds": before, "improved_seconds": after,
                        "time_reduction": (before - after) / before,
                        "changed_operator": base.operator != row.operator,
                        "stages": {stage: {"baseline": base.stages[stage].model_dump(),
                                            "improved": row.stages[stage].model_dump()} for stage in STAGES},
                        "draft_seconds": {"baseline": base.draft_seconds, "improved": row.draft_seconds},
                        "correction_seconds": {"baseline": base.correction_seconds, "improved": row.correction_seconds},
                        "limitations": row.limitations, "refinds": row.refinds,
                        "mandatory_fields": row.mandatory_fields,
                        "post_pass_omissions": row.post_pass_omissions, "unsafe_passes": row.unsafe_passes,
                        "confirmation_required_fraction": (row.confirmation_required_fields / row.mandatory_fields
                                                           if row.confirmation_required_fields is not None else None),
                        "baseline_confirmation_required_fraction": (base.confirmation_required_fields / base.mandatory_fields
                                                                    if base.confirmation_required_fields is not None else None),
                        "readiness_reason_counts": row.readiness_reason_counts,
                        "corrected_fraction": row.corrected_fields / row.mandatory_fields,
                        "populated_fraction": row.populated_fields / row.mandatory_fields,
                        "correction_reasons": row.correction_reasons})
    slower = sum(r["time_reduction"] < 0 for r in results)
    reduction = median(r["time_reduction"] for r in results) if results else None
    validation = [r["time_reduction"] for r in results if r["cohort"] == "validation"]
    setup = improved.get("registry_setup_seconds")
    complete = (len(rows) == 5 and len(correction_pairs) == 2 and type(setup) in {int, float} and 0 <= setup < float("inf")
                and all(r.confirmation_required_fields is not None for r in [*protocol.baseline, *rows]))
    safety = any(row.post_pass_omissions or row.unsafe_passes for row in rows)
    corrections_ok = len(correction_pairs) == 2 and sum(p[1] for p in correction_pairs) <= (
        sum(p[0] for p in correction_pairs) * protocol.targets.max_draft_correction_ratio)
    status = "incomplete"
    if safety:
        status = "hold_safety"
    elif slower >= protocol.targets.stop_if_slower_cases:
        status = "hold_value"
    elif complete:
        status = "targets_met" if (reduction >= protocol.targets.median_time_reduction and corrections_ok
                                   and all(r.refinds <= protocol.targets.max_refinds for r in rows)) else "targets_not_met"
    savings = sum(r["baseline_seconds"] - r["improved_seconds"] for r in results)
    return {"status": status, "protocol_sha256": expected, "completed_cases": len(rows),
            "missing_cases": sorted(set(CASES) - {r.case_id for r in rows}), "slower_cases": slower,
            "median_time_reduction": reduction, "validation_median_time_reduction": median(validation) if validation else None,
            "draft_correction_target_met": corrections_ok, "registry_setup_seconds": setup,
            "observed_savings_seconds": savings, "cases": results,
            "notice": "사람이 입력한 초기 5건 관찰 결과입니다. 참가·충족·제출 준비 승인을 변경하지 않습니다."}


def lock_validation(folder: Path, *, at: datetime | None = None) -> dict:
    at = at or datetime.now(UTC)
    result = report(folder)
    if result["completed_cases"] != 1 or result["cases"][0]["case_id"] != "A":
        raise ValueError("A만 완료된 시점에 B~E의 검증 버전을 고정하세요.")
    if result["status"] == "hold_safety":
        raise ValueError("A의 안전 결함을 먼저 해결하고 별도 평가 기록을 남기세요.")
    improved = json.loads((folder / "improved.json").read_text(encoding="utf-8"))
    rows = [Measurement.model_validate(row) for row in improved["runs"]]
    if not improved["code_revision"].strip() or not improved["rule_version"].strip() or rows[0].completed_at >= at:
        raise ValueError("A 완료 후 검증할 코드/규칙 버전을 지정하세요.")
    release = {"protocol_sha256": result["protocol_sha256"], "locked_at": at.isoformat(),
               "code_revision": improved["code_revision"], "rule_version": improved["rule_version"],
               "development_run_sha256": digest([row.model_dump(mode="json") for row in rows])}
    release["sha256"] = digest(release)
    write_new(folder / "validation-release.json", release)
    return release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "freeze", "lock-validation", "report"])
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.folder)
            print("측정 양식을 생성했습니다. 실제 관찰값을 입력한 뒤 freeze를 실행하세요.")
        elif args.command == "freeze":
            frozen = freeze(args.folder)
            print(json.dumps({key: frozen[key] for key in ("sha256", "frozen_at")}, indent=2))
        elif args.command == "lock-validation":
            print(json.dumps(lock_validation(args.folder), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(report(args.folder), ensure_ascii=False, indent=2))
    except ValidationError as exc:
        messages = [f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in exc.errors()]
        parser.exit(2, "평가 기록 확인 필요:\n" + "\n".join(messages) + "\n")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"평가 기록 확인 필요: {exc}\n")


if __name__ == "__main__":
    main()
