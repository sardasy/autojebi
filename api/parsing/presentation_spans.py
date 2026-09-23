"""Display-only ranges into legacy itertext; never rewrite canonical source text."""

import hashlib
import json

LIMIT = 2_000_000


def hwpx_spans(root, text: str, locator: str, offset: int = 0) -> dict:
    tokens: list[str] = []
    spans: list[dict] = []
    position = 0

    def append(value: str | None) -> None:
        nonlocal position
        if value:
            position += bool(tokens) + len(value)
            tokens.append(value)

    def visit(node, path: str) -> None:
        start = position + bool(tokens)
        append(node.text)
        children = list(node)
        for index, child in enumerate(children):
            visit(child, f"{path}/{index}")
            append(child.tail)
        kind = node.tag.rsplit("}", 1)[-1]
        # Row ranges preserve label/value relationships. Leaf paragraphs avoid entire-document spans.
        if kind == "tr" or (kind == "p" and not any(
            n is not node and n.tag.rsplit("}", 1)[-1] == "p" for n in node.iter()
        )):
            if position > start:
                spans.append({"start": offset + start, "end": offset + position,
                              "locator": f"{locator}#xml={path}",
                              "kind": "row" if kind == "tr" else "paragraph"})

    visit(root, "0")
    if " ".join(tokens) != text:
        return {"version": 1, "status": "partial", "spans": [],
                "issues": ["presentation_text_mismatch"]}
    if len(json.dumps(spans, ensure_ascii=False).encode()) > LIMIT:
        return {"version": 1, "status": "partial", "spans": [],
                "issues": ["presentation_limit"]}
    return {"version": 1, "status": "complete", "spans": spans, "issues": []}


def presentation(spans: list[dict], issues: list[str], text: str) -> dict:
    if len(json.dumps(spans, ensure_ascii=False).encode()) > LIMIT:
        spans, issues = [], [*issues, "presentation_limit"]
    return {"version": 1, "status": "partial" if issues else "complete", "spans": spans,
            "issues": sorted(set(issues)), "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
