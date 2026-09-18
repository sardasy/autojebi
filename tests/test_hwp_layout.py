import hashlib
import threading

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.hwp_worker.app import create_app
from api.hwp_worker.layout import Block, Layout, Run, compile_markdown
from api.hwp_worker.paths import AllowedPaths
from api.hwp_worker.recovery import RecoveryGuard, RecoveryRequired
from api.workspace.hwp_layout import proposal_text


def test_layout_preserves_order_tables_emphasis_long_korean_and_page_breaks():
    body = "# 제목\n\n**강조** 및 *기울임*\n\n| 요구 | 제안 |\n|---|---|\n| A | B |\n\n<!-- page -->\n\n" + "긴 한글 본문 " * 1000
    layout, values, manifest = compile_markdown(body)
    assert layout.fields() == list(values) == [m["field"] for m in manifest]
    assert any(b.kind == "page_break" for b in layout.blocks)
    table = next(b for b in layout.blocks if b.kind == "table")
    assert [[values[c[0].field] for c in row] for row in table.rows] == [["요구", "제안"], ["A", "B"]]
    assert any(r.bold for b in layout.blocks for r in b.runs)
    assert any(r.italic for b in layout.blocks for r in b.runs)
    assert list(values.values())[-1] == "긴 한글 본문 " * 999 + "긴 한글 본문"
    assert manifest[-1]["text_sha256"] == hashlib.sha256(list(values.values())[-1].encode()).hexdigest()
    assert compile_markdown(body)[0].checksum() == layout.checksum()


@pytest.mark.parametrize("text", ["<script>alert(1)</script>", "![x](https://example.com/x.png)", "```python\nprint(1)\n```", "> quote", "<!-- other -->"])
def test_layout_rejects_unsupported_instead_of_omitting(text):
    with pytest.raises(ValueError):
        compile_markdown(text)


def test_duplicate_fields_and_ragged_tables_rejected():
    with pytest.raises(ValidationError):
        Layout(blocks=[Block(kind="paragraph", runs=[Run(field="same"), Run(field="same")])])
    with pytest.raises(ValidationError):
        Block(kind="table", rows=[[[Run(field="a")]], [[Run(field="b")], [Run(field="c")]]])


def test_numbered_lists_and_link_targets_are_preserved():
    _, values, _ = compile_markdown("3. first\n4. [maker](https://example.com/spec)\n\n<https://example.com>")
    joined = "".join(values.values())
    assert joined == "3. first4. maker (https://example.com/spec)https://example.com"


def test_full_draft_first_without_mutating_sections():
    original = {"proposal_sections": [{"text": "납기 추가 검토"}, {"text": "# 제안서\n\n전체 본문"}]}
    text = proposal_text(original)
    assert text.startswith("# 제안서") and text.endswith("납기 추가 검토")
    assert original["proposal_sections"][0]["text"] == "납기 추가 검토"


def test_timeout_latch_survives_late_success_and_new_guard(tmp_path):
    guard = RecoveryGuard(tmp_path)
    started, finish = threading.Event(), threading.Event()
    failures = []
    def work():
        try:
            guard.run(lambda: (started.set(), finish.wait(2), {})[-1])
        except RecoveryRequired as exc:
            failures.append(exc)
    thread = threading.Thread(target=work)
    thread.start()
    assert started.wait(1)
    guard.mark_uncertain()
    finish.set()
    thread.join(3)
    assert failures and not RecoveryGuard(tmp_path).available()


def test_template_endpoint_auth_path_and_serial_thread(tmp_path, monkeypatch):
    roots = [tmp_path / n for n in ("templates", "sources", "outputs")]
    for root in roots:
        root.mkdir()
    token = "x" * 32
    driver = type("Driver", (), {"availability": lambda self: {"available": True}})()
    called = []
    def author(base, output, layout, visible):
        called.append(threading.current_thread().name)
        return {"output_path": str(output)}
    monkeypatch.setattr("api.hwp_worker.authoring.create_template", author)
    body = {"operation_id": "test", "output_path": "new.hwp", "layout": {"blocks": [{"kind": "paragraph", "runs": [{"field": "body"}]}]}}
    with TestClient(create_app(token=token, paths=AllowedPaths(*roots), driver=driver)) as client:
        assert client.post("/document/create-template", json=body).status_code == 401
        headers = {"X-Agent-Token": token}
        assert client.post("/document/create-template", json={**body, "output_path": "../escape.hwp"}, headers=headers).status_code == 422
        assert not called
        assert client.post("/document/create-template", json=body, headers=headers).status_code == 200
        assert called == ["hwp-com-owner"]
