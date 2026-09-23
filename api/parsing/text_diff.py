"""Bounded hierarchical sequence comparison in Unicode codepoints."""
from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

SPACE = "\t\n\r \u00a0" + "".join(chr(c) for c in range(0x2000, 0x200b)) + "\u2028\u2029\u202f\u205f\u3000"
NUMBER = r"[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
WORDS = re.compile(rf"{NUMBER}|[\w]+|[{SPACE}]+|[^\w{SPACE}]", re.UNICODE)
MAX_WORK = 2_000_000
MAX_CHANGES = 500


class Budget:
    def __init__(self, seconds: float = 5) -> None:
        self.work = 0
        self.deadline = time.monotonic() + seconds
        self.truncated = False

    def allow(self, a: int, b: int) -> bool:
        self.work += a * b
        if self.work > MAX_WORK or time.monotonic() > self.deadline:
            self.truncated = True
            return False
        return True


def whitespace_equal(a: str, b: str) -> bool:
    return a.translate({ord(c): None for c in SPACE}) == b.translate({ord(c): None for c in SPACE})


def diff_text(before: str, after: str, *, budget: Budget | None = None,
              uncertain: list[str] | None = None) -> dict:
    budget = budget or Budget()
    changes: list[dict] = []

    def emit(a: str, b: str, x: int, y: int) -> None:
        if len(changes) >= MAX_CHANGES:
            budget.truncated = True
            return
        kind = "whitespace" if whitespace_equal(a, b) else "content"
        if any(value and (value in a or value in b) for value in uncertain or []):
            kind = "unclassified"
        changes.append({"kind": kind, "before_start": x, "before_end": x + len(a),
                        "after_start": y, "after_end": y + len(b), "before": a, "after": b,
                        "before_context": before[max(0, x-40):x],
                        "after_context": after[y+len(b):y+len(b)+40]})

    def tokens(value: str, level: int) -> list[str]:
        if level == 0:
            return value.splitlines(keepends=True)
        if level == 1:
            return WORDS.findall(value)
        # Numbers remain atomic even at the character refinement stage.
        return re.findall(rf"{NUMBER}|[\s\S]", value)

    def visit(a: str, b: str, x: int, y: int, level: int) -> None:
        if a == b or budget.truncated:
            return
        if not budget.allow(0, 0):
            return
        if not a or not b:
            emit(a, b, x, y)
            return
        aa, bb = tokens(a, level), tokens(b, level)
        if not budget.allow(len(aa), len(bb)):
            return
        xs, ys = [0], [0]
        for v in aa:
            xs.append(xs[-1]+len(v))
        for v in bb:
            ys.append(ys[-1]+len(v))
        for op, i, j, k, stop in SequenceMatcher(None, aa, bb, autojunk=False).get_opcodes():
            if op == "equal":
                continue
            left, right = "".join(aa[i:j]), "".join(bb[k:stop])
            if op == "replace" and level < 2:
                visit(left, right, x+xs[i], y+ys[k], level+1)
            else:
                emit(left, right, x+xs[i], y+ys[k])
    visit(before, after, 0, 0, 0)
    return {"changes": changes, "completion": "truncated" if budget.truncated else "complete"}
