import hashlib
from pathlib import Path

import pytest
from PIL import Image

from api.hwp_worker.layout import Layout
from api.services.hwp_agent_client import PutFieldsOutcome
from api.workspace import hwp_layout
from api.workspace.errors import WorkspaceError
from tests.test_workspace_hwp_validation import hwp_bytes


@pytest.fixture
def layout_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HWP_TEMPLATE_ROOT", str(tmp_path))
    content = hwp_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    base = tmp_path / "base.hwp"
    base.write_bytes(content)
    monkeypatch.setattr(hwp_layout, "template_file", lambda _: (base, checksum))
    monkeypatch.setattr("api.workspace.service.blockers", lambda _: [])
    mutation = {"kind": "none"}

    class Client:
        def __init__(self, **kwargs):
            pass

        def create_template(self, **kwargs):
            assert kwargs["operation_id"] == "job-layout"
            layout = Layout.model_validate(kwargs["layout"])
            Path(kwargs["output_path"]).write_bytes(content)
            return {"output_path": kwargs["output_path"], "sha256": checksum, "base_sha256": checksum,
                    "layout_sha256": layout.checksum(), "fields": layout.fields(),
                    "field_occurrences": [{"field": f, "occurrence": 0} for f in layout.fields()],
                    "lifecycle": ["opened", "saved", "closed", "reopened", "closed", "quit"]}

        def put_fields(self, **kwargs):
            assert kwargs["render_pages"] is True
            output = Path(kwargs["output_path"])
            output.write_bytes(content)
            fields = [{"field": f, "occurrence": 0} for f in kwargs["values"]]
            readback = [{**f, "value": kwargs["values"][f["field"]]} for f in fields]
            if mutation["kind"] == "missing_body":
                readback[-1]["value"] = "omitted"
            page = output.parent / "draft-pages/page-001.png"
            page.parent.mkdir()
            Image.new("RGB", (794, 1122), "white").save(page)
            pages = [{"number": 1, "path": str(page), "width": 794, "height": 1122,
                      "sha256": hashlib.sha256(page.read_bytes()).hexdigest(), "edge_check": "passed"}]
            raw = {"fields": list(kwargs["values"]), "replaced": list(kwargs["values"]), "missing": [],
                   "remaining_placeholders": [], "pages": [] if mutation["kind"] == "no_pages" else pages,
                   "verification": {"contract_version": 1, "template_sha256": checksum, "output_sha256": checksum,
                        "template_fields": fields, "saved_fields": fields, "readback": readback,
                        "lifecycle": ["opened", "written", "saved", "closed", "reopened", "readback", "closed", "quit"]}}
            return PutFieldsOutcome(str(output), raw["replaced"], [], [], raw)

    monkeypatch.setattr(hwp_layout, "HwpAgentClient", Client)
    job = {"id": "job", "snapshot": {"proposal_sections": [{"text": "# 제안서\n\n전체 본문"}]}}
    preview = {"template": {"template_version": "v1"}, "mappings": [{"context_path": "proposal.body"}], "body_mapped": True}
    return job, preview, tmp_path, mutation


def test_layout_generation_keeps_logical_and_physical_proof(layout_run):
    job, preview, folder, _ = layout_run
    result = hwp_layout.run_layout_hwp(job, preview, folder)
    assert result["logical_input"] == "# 제안서\n\n전체 본문"
    assert len(result["input_values"]) == len(result["body_manifest"]) == 2
    assert result["verified"] and result["validation"]["body_coverage"] == "passed"
    assert result["page_count"] == 1 and result["validation"]["layout_review"] == "required"
    assert result["warnings"]


@pytest.mark.parametrize("kind", ["missing_body", "no_pages"])
def test_layout_generation_rejects_missing_body_or_page_proof(layout_run, kind):
    job, preview, folder, mutation = layout_run
    mutation["kind"] = kind
    with pytest.raises(WorkspaceError) as caught:
        hwp_layout.run_layout_hwp(job, preview, folder)
    assert caught.value.detail["code"] == "layout_verification_failed"
