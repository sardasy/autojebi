"""Import source-quoted pending requirements and export a local review package."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("notice_no")
    parser.add_argument("requirements", type=Path)
    parser.add_argument("--base", default="http://127.0.0.1:3002")
    args = parser.parse_args()
    if args.base != "http://127.0.0.1:3002":
        parser.error("Only the local validation environment is supported")
    prefix = "/notices/" + quote(args.notice_no, safe="")
    output = Path("data/workspace/preparation") / args.notice_no
    if not output.resolve().is_relative_to(Path("data/workspace/preparation").resolve()):
        parser.error("Invalid notice number")
    output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.base + "/api/v2", headers={"Origin": args.base}, timeout=120) as client:
        def request(path: str, body: dict | None = None) -> dict:
            response = client.get(path) if body is None else client.post(path, json=body)
            response.raise_for_status()
            return response.json()

        ws = request(prefix + "/workspace")
        source = next(d for d in ws["inputs"]["documents"] if d["name"].endswith(".pdf") and d["role"] == "notice_source")
        for entry in json.loads(args.requirements.read_text(encoding="utf-8")):
            if entry["quote"] not in source["text"]:
                raise ValueError("Source quote mismatch: " + entry["text"])
            if any(r["text"] == entry["text"] and r["quote"] == entry["quote"] for r in ws["inputs"]["requirements"]):
                continue
            ws = request(prefix + "/requirements", {
                **entry, "version": ws["version"], "document_id": source["id"],
                "review_status": "pending", "compliance": "unassessed",
            })
        generated = []
        for kind in ("excel", "package"):
            key = f"prepare-{kind}-{ws['version']}"
            job = request(prefix + "/jobs", {"kind": kind, "input_version": ws["version"], "idempotency_key": key})
            deadline = time.monotonic() + 120
            while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(2)
                job = request("/jobs/" + job["id"])
            if job["status"] != "succeeded":
                raise RuntimeError(f"{kind}: {job['status']}; inspect job {job['id']}")
            response = client.get("/jobs/" + job["id"] + "/download")
            response.raise_for_status()
            digest = hashlib.sha256(response.content).hexdigest()
            if digest != job["result"]["sha256"]:
                raise ValueError("Downloaded artifact checksum mismatch")
            path = output / ("requirements.xlsx" if kind == "excel" else "review-package.zip")
            path.write_bytes(response.content)
            generated.append({"id": job["id"], "kind": kind, "quality": job["quality"], "sha256": digest, "path": str(path)})
        ws = request(prefix + "/workspace")
        report = {"notice_no": args.notice_no, "version": ws["version"], "decision": ws["decision"], "ready": ws["ready"], "requirements": len(ws["inputs"]["requirements"]), "source_attachments": ws["source_attachments"], "blockers": ws["blockers"], "generated": generated}
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"notice_no": args.notice_no, "requirements": report["requirements"], "ready": ws["ready"], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
