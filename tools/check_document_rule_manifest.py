"""Ensure a pull request cannot rewrite or remove previously published rule hashes."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

MANIFEST = "tests/fixtures/document_rule_hashes.json"


def check_immutable(previous: dict, current: dict) -> None:
    for rule, versions in previous.items():
        for version, digest in versions.items():
            if current.get(rule, {}).get(version) != digest:
                raise ValueError(f"Immutable rule changed: {rule} v{version}; add a new version")


def main() -> None:
    base = os.environ.get("DOCUMENT_RULE_BASE", "HEAD")
    if not base or set(base) == {"0"}:
        return
    # The first introduction has no previous manifest. A missing git base is an error.
    subprocess.run(["git", "rev-parse", "--verify", base], check=True, capture_output=True)
    files = subprocess.run(["git", "ls-tree", "--name-only", base, "--", MANIFEST],
                           check=True, capture_output=True, text=True).stdout
    if not files.strip():
        return
    previous = subprocess.run(["git", "show", f"{base}:{MANIFEST}"], check=True,
                              capture_output=True, encoding="utf-8").stdout
    check_immutable(json.loads(previous), json.loads(Path(MANIFEST).read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
