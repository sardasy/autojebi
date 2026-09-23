"""Read local files without COM or external services; save candidate reports for review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from api.parsing.attachment_text import extract_hwpx
from api.parsing.hwp_validation import read_hwp_output
from api.parsing.kordoc import compare_text
from api.services.kordoc_client import KordocError, parse_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    folder = Path("data/workspace/kordoc-validation") / uuid4().hex
    folder.mkdir(parents=True)
    summaries = []
    for index, path in enumerate(args.files):
        content = read_hwp_output(path)
        checksum = hashlib.sha256(content).hexdigest()
        item = {"file": str(path.resolve()), "source_sha256": checksum, "verified": False}
        try:
            candidate = parse_document(content, path.suffix)
            # HWP baseline requires an existing saved extraction; never invoke COM here.
            baseline = extract_hwpx(content)["text"] if path.suffix.lower() == ".hwpx" else ""
            result = {**item, "candidate": candidate.model_dump(), "baseline_text": baseline,
                      "comparison": compare_text(baseline, candidate.text)}
            (folder / f"{index:02d}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            item.update(status="parsed", chars=len(candidate.text), tables=len(candidate.tables),
                        fragments=len(candidate.fragments), page_mode=candidate.page_mode,
                        baseline_available=bool(baseline), warnings=candidate.warnings)
        except KordocError as exc:
            item.update(status="failed", error_code=str(exc))
        item["source_unchanged"] = hashlib.sha256(read_hwp_output(path)).hexdigest() == checksum
        summaries.append(item)
    (folder / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(folder.resolve()), "results": [
        {key: value for key, value in item.items() if key not in {"file", "source_sha256"}}
        for item in summaries]}, ensure_ascii=False))
    if any(item["status"] != "parsed" or not item["source_unchanged"] for item in summaries):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
