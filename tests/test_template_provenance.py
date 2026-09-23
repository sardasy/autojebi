import hashlib
import json
from pathlib import Path

import pytest

from api.db.tables import document_field_mappings, hwp_templates
from api.hwp_worker.layout import Layout
from api.workspace.errors import WorkspaceError
from api.workspace.hwp_inspection import inspect_template
from api.workspace.template_provenance import (
    INVALID_WARNING,
    UNCLASSIFIED_WARNING,
    VALIDATION_WARNING,
    confirm_provenance_unchanged,
    content_record_path,
    inspect_provenance,
    metadata_path,
    record_validation_derivative,
    register_source_form,
    require_generation_provenance,
    review_provenance_issues,
    write_skeleton_metadata,
)
from tests.test_workspace_hwp_validation import hwp_bytes
from tools.prepare_default_hwp_templates import prepare


@pytest.fixture
def template(tmp_path, monkeypatch):
    monkeypatch.setenv("HWP_TEMPLATE_ROOT", str(tmp_path))
    path = tmp_path / "bid.hwp"
    path.write_bytes(hwp_bytes())
    return {"template_key": "bid_form", "template_path": str(path)}, path


def mark(template):
    value, path = template
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    write_skeleton_metadata(path, value["template_key"], digest, "fixture-generation")
    return inspect_provenance(value)


def test_existing_default_stays_unclassified_and_generation_does_not_imply_approval(template):
    value, path = template
    proof = inspect_provenance(value)
    assert proof["state"] == "unclassified" and proof["generation_allowed"]
    assert proof["approval_allowed"] is False and not metadata_path(path).exists()
    assert review_provenance_issues({"template_key": "bid_form"}) == [UNCLASSIFIED_WARNING]
    assert review_provenance_issues({}, "proposal") == [UNCLASSIFIED_WARNING]
    assert review_provenance_issues({}, "proposal_layout_v1") == []


def test_metadata_persists_exact_file_origin_and_inspection_exposes_validation_warning(template):
    value, path = template
    proof = mark(template)

    class Worker:
        def health(self):
            return True

        def inspect_fields(self, filename, **kwargs):
            return {"sha256": hashlib.sha256(Path(filename).read_bytes()).hexdigest(),
                    "fields": ["title"], "field_occurrences": [{"field": "title", "occurrence": 0}]}

    inspection = inspect_template(value, [{"hwp_field_name": "title", "required": True}], Worker())
    assert inspection["inspection_passed"] is True
    assert inspection["template_provenance"] == proof
    assert VALIDATION_WARNING in inspection["warnings"]
    assert proof["state"] == "validation_only" and proof["metadata_sha256"]
    assert proof["template_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert review_provenance_issues({"template_provenance": proof,
                                   "template_sha256": proof["template_sha256"]}) == [VALIDATION_WARNING]
    with pytest.raises(FileExistsError):
        mark(template)


@pytest.mark.parametrize("corruption", ["invalid_json", "purpose", "hash", "key", "extra", "file"])
def test_changed_or_invalid_metadata_fails_closed_before_worker(template, corruption):
    value, path = template
    proof = mark(template)
    sidecar = metadata_path(path)
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    if corruption == "invalid_json":
        sidecar.write_text("not json", encoding="utf-8")
    elif corruption == "file":
        path.write_bytes(path.read_bytes() + b"changed")
    else:
        changes = {"purpose": ("purpose", "official"), "hash": ("sha256", "0" * 64),
                   "key": ("template_key", "other"), "extra": ("approval_allowed", True)}
        key, val = changes[corruption]
        metadata[key] = val
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    assert inspect_provenance(value)["state"] == "invalid"
    with pytest.raises(WorkspaceError) as caught:
        require_generation_provenance(value, path, proof["template_sha256"])
    assert caught.value.detail["code"] == "template_provenance_invalid"


def test_removed_or_reformatted_metadata_invalidates_generation_and_saved_review(template):
    value, path = template
    proof = mark(template)
    metadata_path(path).write_bytes(metadata_path(path).read_bytes() + b" ")
    with pytest.raises(WorkspaceError):
        confirm_provenance_unchanged(value, path, proof["template_sha256"], proof)
    # Dropping metadata cannot promote a default skeleton to an approvable template.
    metadata_path(path).unlink()
    assert inspect_provenance(value)["approval_allowed"] is False
    with pytest.raises(WorkspaceError):
        confirm_provenance_unchanged(value, path, proof["template_sha256"], proof)


def test_untracked_nondefault_review_rechecks_current_file_and_metadata(template):
    value, path = template
    value["template_key"] = "official_fixture"
    proof = inspect_provenance(value)
    result = {"template_key": value["template_key"], "template_provenance": proof,
              "template_sha256": proof["template_sha256"]}
    assert review_provenance_issues(result) == []
    metadata_path(path).write_text("{}", encoding="utf-8")
    assert review_provenance_issues(result) == [INVALID_WARNING]
    assert review_provenance_issues({**result, "template_provenance": {"approval_allowed": True}})


def test_generator_installs_metadata_before_new_file_and_preserves_existing(
    sqlite_engine, tmp_path, monkeypatch,
):
    monkeypatch.setenv("HWP_TEMPLATE_ROOT", str(tmp_path))
    monkeypatch.setenv("HWP_OUTPUT_ROOT", str(tmp_path))
    with sqlite_engine.begin() as conn:
        template_id = conn.execute(hwp_templates.insert().values(template_key="bid_form",
            kind="bid_form", name="TEST ONLY", template_path="generated.hwp")).inserted_primary_key[0]
        conn.execute(document_field_mappings.insert().values(template_id=template_id,
            hwp_field_name="title", context_path="notice.title", required=True))

    class Worker:
        def __init__(self, **kwargs):
            pass

        def diagnostics(self):
            return {"available": True}

        def create_template(self, **kwargs):
            layout = Layout.model_validate(kwargs["layout"])
            content = hwp_bytes()
            Path(kwargs["output_path"]).write_bytes(content)
            return {"output_path": kwargs["output_path"], "sha256": hashlib.sha256(content).hexdigest(),
                "base_sha256": None, "fields": layout.fields(),
                "field_occurrences": [{"field": field, "occurrence": 0} for field in layout.fields()],
                "layout_sha256": layout.checksum(), "lifecycle": ["created", "saved", "closed", "reopened", "closed", "quit"]}

    monkeypatch.setattr("api.services.hwp_agent_client.HwpAgentClient", Worker)
    report = prepare("bid_form")
    assert report["status"] == "created_skeleton"
    path = tmp_path / "generated.hwp"
    assert metadata_path(path).is_file()
    assert report["provenance"]["template_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["provenance"]["approval_allowed"] is False
    original = path.read_bytes(), metadata_path(path).read_bytes()
    assert prepare("bid_form")["status"] == "exists_kept"
    assert original == (path.read_bytes(), metadata_path(path).read_bytes())


def test_v2_template_catalog_exposes_current_provenance_without_changing_legacy(client, sqlite_engine, template):
    value, _ = template
    mark(template)
    with sqlite_engine.begin() as conn:
        conn.execute(hwp_templates.insert().values(**value, name="TEST ONLY", kind="bid_form"))
    response = client.get("/v2/hwp-templates")
    assert response.status_code == 200, response.text
    record = response.json()["items"][0]
    assert record["template_key"] == "bid_form"
    assert record["provenance"]["state"] == "validation_only"
    assert record["provenance"]["approval_allowed"] is False
    assert record["provenance"]["metadata_sha256"]
    assert record["provenance"]["content_record_sha256"]
    assert "provenance" not in client.get("/documents/hwp-templates").json()["items"][0]


def register(template, **overrides):
    value, path = template
    options = {"source_reference": "fixture://official-form", "reviewer_id": "fixture-admin",
               "review_note": "TEST ONLY: labels and official wording compared", "human_reviewed": True}
    return register_source_form(value, hashlib.sha256(path.read_bytes()).hexdigest(), **(options | overrides))


def test_skeleton_copied_under_new_key_cannot_be_promoted_or_lose_origin(template):
    value, path = template
    proof = mark(template)
    copy = path.with_name("renamed.hwp")
    copy.write_bytes(path.read_bytes())
    renamed = {"template_key": "official_copy", "template_path": str(copy)}
    assert inspect_provenance(renamed)["state"] == "validation_only"
    assert inspect_provenance(renamed)["approval_allowed"] is False
    assert review_provenance_issues({"template_key": "official_copy",
        "template_sha256": proof["template_sha256"]}) == [VALIDATION_WARNING]
    with pytest.raises(ValueError, match="cannot_be_promoted"):
        register((renamed, copy))
    assert not metadata_path(copy).exists()


def test_filled_validation_copy_retains_its_origin_as_another_template(template):
    _, path = template
    proof = mark(template)
    generated = path.with_name("filled.hwp")
    generated.write_bytes(hwp_bytes(compressed=True))
    checksum = hashlib.sha256(generated.read_bytes()).hexdigest()
    record_validation_derivative(proof, checksum)
    renamed = {"template_key": "filled_as_template", "template_path": str(generated)}
    assert inspect_provenance(renamed)["approval_allowed"] is False
    with pytest.raises(ValueError, match="cannot_be_promoted"):
        register((renamed, generated))


@pytest.mark.parametrize("options", [{"human_reviewed": False}, {"source_reference": " "},
                                    {"reviewer_id": ""}, {"review_note": ""}])
def test_source_registration_requires_explicit_human_origin_review(template, options):
    with pytest.raises(ValueError):
        register(template, **options)
    assert inspect_provenance(template[0])["approval_allowed"] is False


def test_replacing_skeleton_with_reviewed_source_requires_old_metadata_hash(template):
    value, path = template
    old = mark(template)
    original_metadata = metadata_path(path).read_bytes()
    path.write_bytes(hwp_bytes(compressed=True))
    assert inspect_provenance(value)["state"] == "invalid"
    with pytest.raises(ValueError, match="metadata_hash_confirmation"):
        register(template)
    proof = register(template, expected_metadata_sha256=old["metadata_sha256"])
    assert proof["state"] == "reviewed_source" and proof["approval_allowed"]
    assert proof["template_sha256"] != old["template_sha256"]
    archive = content_record_path(proof["template_sha256"]).parent / ("history-" + old["metadata_sha256"] + ".json")
    assert archive.read_bytes() == original_metadata
    assert review_provenance_issues({"template_provenance": proof,
        "template_sha256": proof["template_sha256"]}, "bid_form") == []
    metadata_path(path).write_bytes(metadata_path(path).read_bytes() + b" ")
    assert review_provenance_issues({"template_provenance": proof,
        "template_sha256": proof["template_sha256"]}, "bid_form") == [INVALID_WARNING]


@pytest.mark.parametrize("corruption", ["missing", "invalid"])
def test_missing_or_corrupt_content_record_never_trusts_sidecar(template, corruption):
    value, _ = template
    proof = mark(template)
    record = content_record_path(proof["template_sha256"])
    if corruption == "missing":
        record.unlink()
    else:
        record.write_text("{}", encoding="utf-8")
    assert inspect_provenance(value)["state"] == "invalid"
