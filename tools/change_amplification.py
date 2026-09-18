"""Auxiliary: change amplification of v2 feature commits (refactor pipeline, stage 3).

Observed value: median number of non-test source files under ``api/`` and ``frontend/src``
touched per v2 feature commit. See docs/refactor/2026-09-18-refactor-pipeline.md.

    python tools/change_amplification.py                  # whole history
    python tools/change_amplification.py --since 2026-09-18 --until 2026-10-16
    python tools/change_amplification.py --rev-range 0fae1c6..HEAD --verbose
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
from dataclasses import dataclass

# Paths that mark a commit as touching the v2 slice.
V2_MARKERS = (
    "api/workspace/",
    "api/routers/workspace.py",
    "api/routers/requirement_candidates.py",
    "api/routers/notice_forms.py",
    "frontend/src/components/Workspace",
    "frontend/src/components/NoticeForm",
    "frontend/src/lib/workspace",
    "frontend/src/app/workspace/",
    "frontend/src/app/api/v2/",
)
SOURCE_ROOTS = ("api/", "frontend/src/")
TEST_PARTS = ("/__tests__/", "/test/", ".test.", ".spec.")
MIGRATION_ROOT = "alembic/"
# Refactor commits themselves are excluded from the metric (stage 3 exclusion rule).
EXCLUDED_PREFIXES = ("refactor", "docs", "test", "chore")
MIN_SAMPLE = 10


@dataclass
class Commit:
    sha: str
    subject: str
    files: list[str]

    @property
    def source_files(self) -> list[str]:
        return [
            f
            for f in self.files
            if f.startswith(SOURCE_ROOTS) and not any(p in f for p in TEST_PARTS)
        ]


def load_commits(args: argparse.Namespace) -> list[Commit]:
    cmd = ["git", "log", "--no-merges", "--name-only", "--format=\x1e%h\x1f%s"]
    if args.since:
        cmd.append(f"--since={args.since}")
    if args.until:
        cmd.append(f"--until={args.until}")
    if args.rev_range:
        cmd.append(args.rev_range)
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    commits = []
    for block in out.split("\x1e"):
        if not block.strip():
            continue
        header, _, body = block.partition("\n")
        sha, _, subject = header.partition("\x1f")
        files = [line.strip() for line in body.splitlines() if line.strip()]
        commits.append(Commit(sha, subject, files))
    return commits


def exclusion_reason(commit: Commit) -> str | None:
    subject = commit.subject.lower()
    if subject.startswith(EXCLUDED_PREFIXES):
        return "prefix"
    if not any(f.startswith(V2_MARKERS) for f in commit.files):
        return "not-v2"
    if not commit.source_files:
        if all(f.startswith(MIGRATION_ROOT) for f in commit.files):
            return "migration-only"
        return "docs/tests-only"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--rev-range")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sample: list[Commit] = []
    for commit in load_commits(args):
        reason = exclusion_reason(commit)
        if args.verbose:
            mark = f"skip:{reason}" if reason else f"{len(commit.source_files):>4} files"
            print(f"{commit.sha} {mark:<22} {commit.subject}")
        if reason is None:
            sample.append(commit)

    counts = [len(c.source_files) for c in sample]
    print(f"v2 feature commits: {len(counts)}")
    if not counts:
        return 0
    print(f"median files/commit: {statistics.median(counts)}")
    print(f"mean files/commit:   {statistics.mean(counts):.1f}")
    if len(counts) < MIN_SAMPLE:
        print(f"HOLD: sample < {MIN_SAMPLE}; extend the attribution window before judging.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
