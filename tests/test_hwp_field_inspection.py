import hashlib

import httpx
import pytest

from api.hwp_fields.__main__ import DEFAULT_MAPPINGS
from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError
from api.workspace.hwp_inspection import mapping_hash


def report(**kwargs):
    return {
        "sha256": "a" * 64,
        "fields": ["body"],
        "field_occurrences": [
            {"field": "body", "occurrence": 0},
            {"field": "body", "occurrence": 1},
        ],
        "lifecycle": ["opened", "closed", "quit"],
        "readback": [{"value": "private text"}],
        **kwargs,
    }


def test_inspection_sends_one_post_and_does_not_return_template_values():
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path, request.content))
        return httpx.Response(200, json=report())

    result = HwpAgentClient(token="x" * 32, transport=httpx.MockTransport(handle)).inspect_fields(
        "test.hwp"
    )
    assert calls == [("POST", "/document/fields", b'{"path":"test.hwp"}')]
    assert len(result["field_occurrences"]) == 2
    assert "readback" not in result and "private text" not in str(result)


def test_current_worker_readback_lifecycle_is_accepted_without_leaking_values():
    client = HwpAgentClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json=report(lifecycle=["opened", "readback", "closed", "quit"]))))
    result = client.inspect_fields("test.hwp")
    assert result["lifecycle"] == ["opened", "readback", "closed", "quit"]
    assert "readback" not in result


@pytest.mark.parametrize(
    "patch",
    [
        {"sha256": "wrong"},
        {"fields": ["unknown"]},
        {"fields": ["body", "body"]},
        {"lifecycle": ["opened", "closed"]},
        {"field_occurrences": [{"field": "body", "occurrence": 1}]},
        {
            "field_occurrences": [
                {"field": "body", "occurrence": 0},
                {"field": "body", "occurrence": 0},
            ]
        },
        {"field_occurrences": [{"field": "bad\x02name", "occurrence": 0}]},
        {"ok": False},
    ],
)
def test_inspection_rejects_inconsistent_or_incomplete_report(patch):
    client = HwpAgentClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=report(**patch)))
    )
    with pytest.raises(HwpAgentError):
        client.inspect_fields("test.hwp")


def test_inspection_timeout_does_not_repeat_com_call():
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("private provider text")

    with pytest.raises(HwpAgentError):
        HwpAgentClient(retries=5, transport=httpx.MockTransport(handle)).inspect_fields("test.hwp")
    assert len(calls) == 1


def test_mapping_identity_changes_with_transform_required_or_template_version():
    template = {"template_key": "proposal", "kind": "proposal", "template_version": "v1"}
    field = {
        "hwp_field_name": "proposal_body",
        "context_path": "proposal.body",
        "required": True,
        "transform": "none",
    }
    original = mapping_hash(template, [field])
    assert len(original) == hashlib.sha256().digest_size * 2
    assert original != mapping_hash({**template, "template_version": "v2"}, [field])
    assert original != mapping_hash(template, [{**field, "required": False}])
    assert original != mapping_hash(template, [{**field, "transform": "truncate_1000"}])
    assert DEFAULT_MAPPINGS["proposal"][0] == ("proposal_body", "proposal.body", True, None, "none")


def test_seeded_proposal_maps_complete_body_without_truncation(sqlite_engine):
    from api.hwp_fields.__main__ import seed
    from api.workspace.execution import hwp_preview

    seed()
    body = "한글 본문과 줄바꿈을 보존합니다.\n" * 100
    inputs = {"company": {}, "notice": {}, "requirements": [], "proposal_sections": [{"text": body}]}
    with sqlite_engine.begin() as conn:
        result = hwp_preview(conn, inputs, "proposal")
    assert result["body_mapped"]
    assert len(result["values"]["proposal_body"]) > 1000
    assert result["values"]["proposal_body"] == body
