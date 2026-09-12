"""Hancom plain-field wire format; never discard whitespace or cell boundaries."""
from __future__ import annotations


def normalize(value: str) -> str:
    # GetFieldText exposes paragraphs as CRLF. Spaces, tabs, and blank paragraphs
    # are document content, not noise: dropping them can conceal lost table cells.
    return value.replace("\r\n", "\n").replace("\r", "\n")


def wire_text(value: str) -> str:
    """Send paragraph delimiters in Hancom's format, including standalone breaks."""
    return normalize(value).replace("\n", "\r\n")


def mismatch_summary(expected: str, actual: str) -> dict:
    """Bounded structural diagnostics without document text, hashes, or field names."""
    wanted, saved = normalize(expected), normalize(actual)
    return {
        "expected_length": len(wanted),
        "actual_length": len(saved),
        "expected_linebreaks": wanted.count("\n"),
        "actual_linebreaks": saved.count("\n"),
        "expected_tabs": wanted.count("\t"),
        "actual_tabs": saved.count("\t"),
        "first_difference": next(
            (i for i, (a, b) in enumerate(zip(wanted, saved, strict=False)) if a != b),
            min(len(wanted), len(saved)),
        ),
    }
