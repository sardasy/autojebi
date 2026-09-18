import pytest

from api.workspace import execution
from api.workspace.errors import WorkspaceError


def test_empty_extraction_explains_unapplied_attachments():
    with pytest.raises(WorkspaceError) as raised:
        execution.extract({"snapshot": {"documents": []}})
    assert raised.value.detail["code"] == "no_source_files"
    assert "결과 반영" in raised.value.detail["next_action"]


@pytest.mark.parametrize("documents", [
    [],
    [{"role": "notice_source", "text": " \n\t"}],
    [{"role": "company_reference", "text": "Reference only"}],
    [{"role": "product_evidence", "text": "Evidence only"}],
])
def test_empty_source_analysis_blocks_before_paid_call(monkeypatch, documents):
    def unexpected_call(*args, **kwargs):
        pytest.fail("An empty source must not reserve a paid call")

    monkeypatch.setattr("api.workspace.executors.analyze.reserve_call", unexpected_call)
    with pytest.raises(WorkspaceError) as raised:
        execution.analyze(None, {"snapshot": {"documents": documents}})
    assert raised.value.detail["code"] == "no_source_text"
    assert "결과 반영" in raised.value.detail["next_action"]
