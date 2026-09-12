from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from api.hwp_worker import authoring
from api.hwp_worker.com_driver import ComDriverError
from api.hwp_worker.layout import compile_markdown


class Params:
    def SetItem(self, *args):
        return True

    def Item(self, *args):
        return self

    def CreateItemArray(self, *args):
        return self


@pytest.fixture
def com(monkeypatch):
    calls, fields = [], []
    hwp = SimpleNamespace(XHwpDocuments=SimpleNamespace(Count=1))

    def run(name):
        calls.append(name)
        assert name != "MoveRight", "field end already positions after the control"
        return True

    def create_action(name):
        calls.append(name)
        return SimpleNamespace(CreateSet=Params, GetDefault=lambda p: True, Execute=lambda p: True)

    def create_field(direction, memo, name):
        fields.append(name)
        return True

    def save(path, *args):
        from pathlib import Path

        Path(path).write_bytes(b"mock HWP, not a live-validated artifact")
        return True

    hwp.HAction = SimpleNamespace(Run=run)
    hwp.CreateAction = create_action
    hwp.CreateField = create_field
    hwp.MoveToField = lambda *args: True
    hwp.SaveAs = save
    session = SimpleNamespace(hwp=hwp, opened=False, lifecycle=[])
    session.enumerate = lambda: [{"field": name, "occurrence": 0} for name in fields]
    session.close = lambda: session.lifecycle.append("closed")
    session.open = lambda path, reopen=False: session.lifecycle.append("reopened" if reopen else "opened")

    @contextmanager
    def operation(visible):
        yield session
        session.lifecycle.append("quit")

    monkeypatch.setattr(authoring, "_operation", operation)
    return session, calls, fields


def test_document_must_be_ready_before_first_edit(com, tmp_path):
    session, calls, fields = com
    session.hwp.XHwpDocuments.Count = 0
    layout, _, _ = compile_markdown("# Heading")
    with pytest.raises(ComDriverError, match="active_document_missing"):
        authoring.create_template(None, tmp_path / "new.hwp", layout, False)
    assert not session.opened and not fields and calls == ["FileNew"]


def test_native_table_and_fields_created_once_without_extra_cursor_move(com, tmp_path):
    _, calls, fields = com
    layout, _, _ = compile_markdown("# Heading\n\n| A | B |\n|---|---|\n| text | |\n\n<!-- page -->\n\nEnd")
    result = authoring.create_template(None, tmp_path / "new.hwp", layout, False)
    assert fields == layout.fields()
    assert calls.count("TableCreate") == 1
    assert calls.count("TableRightCell") == 3
    assert calls.count("BreakPage") == 1
    assert result["lifecycle"] == ["created", "saved", "closed", "reopened", "closed", "quit"]


def test_field_creation_failure_is_not_registered_as_success(com, tmp_path):
    session, _, _ = com
    session.hwp.CreateField = lambda *args: False
    layout, _, _ = compile_markdown("body")
    output = tmp_path / "new.hwp"
    with pytest.raises(ComDriverError, match="field_create_failed"):
        authoring.create_template(None, output, layout, False)
    assert not output.exists()


def test_existing_output_is_never_overwritten(com, tmp_path):
    output = tmp_path / "new.hwp"
    output.write_bytes(b"preserve")
    layout, _, _ = compile_markdown("body")
    with pytest.raises(ComDriverError, match="output_exists"):
        authoring.create_template(None, output, layout, False)
    assert output.read_bytes() == b"preserve"
