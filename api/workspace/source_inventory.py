"""Declared G2B sources, including formats the downloader cannot process."""

from typing import Any

from api.workspace.readiness_issues import IssueCode, ReadinessIssue, issue, render_blockers


def readable_document(document: dict) -> bool:
    return bool(isinstance(document.get("text"), str) and document["text"].strip()
                and (document.get("text_origin") == "manual_confirmed"
                     or document.get("extraction", {}).get("complete", True)))


def source_inventory(inputs: dict) -> list[dict[str, Any]]:
    raw = inputs.get("raw")
    if not isinstance(raw, dict):
        return []
    inventory = []
    for index in range(1, 11):
        url = str(raw.get(f"ntceSpecDocUrl{index}") or "").strip()
        name = str(
            raw.get(f"ntceSpecFileNm{index}") or raw.get(f"ntceSpecDocNm{index}") or ""
        ).strip()
        if not url and not name:
            continue
        documents = [
            d
            for d in inputs.get("documents") or []
            if d.get("role") == "notice_source"
            and type(d.get("attachment_index")) is int
            and d["attachment_index"] == index
            # An explicit empty URL is a manual link to a named URL-less slot.
            and "attachment_url" in d
            and d["attachment_url"] == url
            and d.get("id")
        ]
        state = "missing"
        if documents:
            state = (
                "ready"
                if any(readable_document(d) for d in documents)
                else "unread"
            )
        inventory.append(
            {
                "index": index,
                "name": name or f"g2b-attachment-{index}.bin",
                "url": url,
                "document_ids": list(dict.fromkeys(d["id"] for d in documents)),
                "state": state,
            }
        )
    return inventory


def source_inventory_issues(inputs: dict) -> list[str]:
    return render_blockers(source_readiness_issues(inputs))


def source_readiness_issues(inputs: dict) -> list[ReadinessIssue]:
    return [
        issue(IssueCode.ATTACHMENT_MISSING if item["state"] == "missing" else IssueCode.ATTACHMENT_UNREAD,
              "attachment", str(item["index"]), name=item["name"])
        for item in source_inventory(inputs)
        if item["state"] != "ready"
    ]


def source_text_complete(inputs: dict) -> bool:
    # A readable, explicitly linked conversion can replace an unread original slot.
    covered = {
        document_id
        for item in source_inventory(inputs)
        if item["state"] == "ready"
        for document_id in item["document_ids"]
    }
    sources = [d for d in inputs.get("documents") or [] if d.get("role") == "notice_source"]
    return bool(sources) and all(
        readable_document(d) or d.get("id") in covered
        for d in sources
    )
