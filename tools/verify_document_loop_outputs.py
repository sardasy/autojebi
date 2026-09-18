"""Read-only content comparison of app-generated sample rehearsal artifacts."""

import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    folder = root / "data/workspace/sample-loop" / sys.argv[1]
    report = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    state = report["state"]
    workbook = load_workbook(folder / "requirements.xlsx", read_only=True, data_only=False)
    rows = list(workbook.worksheets[0].values)
    assert len(rows) == 4, "Expected exactly three requirement rows"
    for row, req in zip(rows[1:], state["requirements"], strict=True):
        assert row[0] == req["text"]
        assert row[1] == req["quote"]
        assert row[3] == req["proposed_value"]
        assert row[4] == req["evidence_quote"]
        assert row[6] == "accepted"
    with ZipFile(folder / "review-package.zip") as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["notice_no"] == report["notice_no"]
        assert manifest["input_version"] == state["version"]
        text = archive.read("proposal.txt").decode("utf-8")
        for section in state["sections"]:
            assert section["text"] in text
            assert section["review_status"] == "approved"
        assert "[가상 테스트]" in text
        assert "[검증필요]" not in text
        files = [n for n in archive.namelist() if n.startswith("sources/")]
        actual_hashes = {hashlib.sha256(archive.read(name)).hexdigest() for name in files}
        samples = root / "output/pdf/document-loop-samples"
        expected_hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in samples.glob("*.pdf")}
        assert len(files) == 3 and actual_hashes == expected_hashes
        excel_entries = [n for n in archive.namelist() if n.endswith(".xlsx")]
        assert len(excel_entries) == 1
        assert archive.read(excel_entries[0]) == (folder / "requirements.xlsx").read_bytes()
        reviews = manifest["reviews"]
        assert any(r["action"] == "rejected" for r in reviews)
        checks = {
            "notice_no": report["notice_no"], "requirement_rows": len(rows) - 1,
            "sheets": workbook.sheetnames, "source_pdfs_sha256_match": len(files),
            "proposal_sections_match": len(state["sections"]), "embedded_excel_matches": True,
            "rejection_record_in_manifest": True, "package_entries": archive.namelist(),
            "submission_ready": state["ready"], "hwp_result": state["jobs"][0],
            "findings": report["findings"],
        }
    workbook.close()
    (folder / "artifact-checks.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
