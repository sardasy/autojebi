import copy
import hashlib

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert, update

from api.workspace.backup_audit import audit_references, compare_databases, fingerprint_database


def test_database_fingerprints_detect_value_and_schema_changes():
    engine = create_engine("sqlite://")
    meta = MetaData()
    table = Table("example", meta, Column("id", Integer, primary_key=True), Column("value", String))
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(table), [{"id": 1, "value": "old"}])
    before = fingerprint_database(engine)
    assert before == fingerprint_database(engine)
    with engine.begin() as conn:
        conn.execute(update(table).values(value="new"))
    after = fingerprint_database(engine)
    assert before["tables"]["example"]["data_sha256"] != after["tables"]["example"]["data_sha256"]
    assert before["tables"]["example"]["schema_sha256"] == after["tables"]["example"]["schema_sha256"]
    engine.dispose()


def test_file_references_require_archive_coverage_and_matching_digest(tmp_path):
    checksum = hashlib.sha256(b"verified bytes").hexdigest()
    refs = [{"kind": "workspace", "id": "one", "path": str(tmp_path / "source.pdf"), "sha256": checksum}]
    manifest = {"roots": {"source": str(tmp_path)}, "entries": [{"path": "files/source/source.pdf", "sha256": checksum, "size": 14}]}
    assert audit_references(refs, manifest)["database_hash_matches"] == 1
    manifest["entries"][0]["sha256"] = "f" * 64
    assert audit_references(refs, manifest)["issues"][0]["code"] == "database_file_hash_mismatch"
    manifest["entries"] = []
    assert audit_references(refs, manifest)["complete"] is False


def test_path_only_evidence_and_unbacked_template_are_explicit(tmp_path):
    manifest = {"roots": {"source": str(tmp_path)}, "entries": [{"path": "files/source/source.hwp", "sha256": "a" * 64, "size": 1}]}
    refs = [{"kind": "template", "id": "one", "path": str(tmp_path / "source.hwp"), "sha256": None}]
    assert audit_references(refs, manifest)["path_only_matches"] == 1
    refs.append({"kind": "template", "id": "missing", "path": str(tmp_path / "missing.hwp"), "sha256": None})
    result = audit_references(refs, manifest)
    assert result["complete"] is False
    assert result["issues"] == [{"kind": "template", "id": "missing", "code": "not_archived"}]


def test_schema_difference_never_hidden_by_matching_rows():
    before = {"version": 1, "tables": {"example": {"rows": 1, "data_sha256": "a", "schema_sha256": "b"}}, "sequences": {}}
    after = copy.deepcopy(before)
    after["tables"]["example"]["schema_sha256"] = "c"
    result = compare_databases(before, after)
    assert result["data_equal"] is True
    assert result["sequences_equal"] is True
    assert result["equal"] is False
    assert result["schema_equal"] is False
    assert result["schema_differences"] == ["example"]


def test_missing_tables_and_sequence_changes_block_equality():
    before = {"version": 1, "tables": {"example": {"rows": 1, "data_sha256": "a", "schema_sha256": "b"}}, "sequences": {"example_id_seq": {"last_value": 2, "is_called": True}}}
    after = copy.deepcopy(before)
    after["tables"].clear()
    after["sequences"]["example_id_seq"]["last_value"] = 1
    result = compare_databases(before, after)
    assert result["missing_tables"] == ["example"]
    assert result["data_equal"] is False
    assert result["schema_equal"] is False
    assert result["sequences_equal"] is False
    assert result["equal"] is False
