from __future__ import annotations

import hashlib
import json
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.hwp_worker import com_driver as driver

LIFECYCLE = ["opened", "written", "saved", "closed", "reopened", "readback", "closed", "quit"]


class FakeCom:
    def __init__(self, tmp_path):
        self.template = tmp_path / "template.hwp"
        self.template.write_bytes(b"template for fake COM only")
        self.output = tmp_path / "output.hwpx"
        self.calls = []
        self.failures = set()
        self.wait = 0
        self.names = ["title", "body", "title"]
        self.saved_names = None
        self.data = {("title", 0): "old", ("body", 0): "body", ("title", 1): "old"}
        self.overrides = {}
        self.field_list = None
        self.open_results = [True, True]
        self.save_result = True
        self.write_result = None
        self.quit_result = None
        self.clear_result = None
        self.clear_fail_at = set()
        self.clear_count = 0
        self.open_count = 0
        self.text = "한글 본문\r\nSecond line"
        self.corrupt_on_second_close = False
        self.mutate_template_on_save = False
        self.write_file = True
        self.window = SimpleNamespace(Visible=None)
        self.hwp = SimpleNamespace(
            Open=self.open,
            Clear=self.clear,
            SaveAs=self.save,
            GetFieldList=self.fields,
            GetFieldText=self.read,
            PutFieldText=self.write,
            GetTextFile=self.analyze,
            Quit=self.quit,
            XHwpWindows=SimpleNamespace(Item=self.window_item),
        )
        self.runtime = SimpleNamespace(
            prog_id=driver.PROG_ID,
            com=SimpleNamespace(
                COINIT_APARTMENTTHREADED=2,
                CoInitializeEx=lambda mode: self.record("initialize", mode),
                CoUninitialize=lambda: self.record("uninitialize"),
            ),
            client=SimpleNamespace(DispatchEx=self.dispatch),
            event=SimpleNamespace(
                WAIT_OBJECT_0=0,
                WAIT_ABANDONED=128,
                WAIT_TIMEOUT=258,
                CreateMutex=self.create_mutex,
                WaitForSingleObject=self.wait_mutex,
                ReleaseMutex=lambda handle: self.record("release", handle),
            ),
            api=SimpleNamespace(CloseHandle=lambda handle: self.record("handle_close", handle)),
        )

    def record(self, name, *args):
        self.calls.append((name, args, threading.get_ident()))
        if name in self.failures:
            raise RuntimeError("private-path-and-document-secret")

    def create_mutex(self, security, owned, name):
        self.record("mutex_create", security, owned, name)
        return 123

    def wait_mutex(self, handle, timeout):
        self.record("mutex_wait", handle, timeout)
        return self.wait

    def dispatch(self, name):
        self.record("dispatch", name)
        return self.hwp

    def window_item(self, index):
        self.record("window", index)
        return self.window

    def open(self, path, fmt, options):
        self.record("open", path, fmt, options)
        result = self.open_results[self.open_count]
        self.open_count += 1
        return result

    def fields(self, number, option):
        self.record("fields", number, option)
        if self.field_list is not None:
            return self.field_list
        names = (
            self.saved_names
            if self.open_count == 2 and self.saved_names is not None
            else self.names
        )
        return "\x02".join(names)

    def write(self, name, text):
        self.record("write", name, text)
        for key in self.data:
            if key[0] == name:
                self.data[key] = text
        return self.write_result

    def save(self, path, fmt, options):
        self.record("save", path, fmt, options)
        if self.save_result and self.write_file:
            Path(path).write_bytes(json.dumps(list(self.data.values())).encode())
        if self.mutate_template_on_save:
            self.template.write_bytes(b"changed template")
        return self.save_result

    def clear(self, option):
        self.record("clear", option)
        self.clear_count += 1
        if self.clear_count in self.clear_fail_at:
            raise RuntimeError("private-path-and-document-secret")
        if self.clear_count == 2 and self.corrupt_on_second_close:
            self.output.write_bytes(b"changed during reopen")
        return self.clear_result

    def read(self, selector):
        self.record("read", selector)
        name, occurrence = selector.rsplit("{{", 1)
        key = (name, int(occurrence.removesuffix("}}")))
        return self.overrides.get(key, self.data.get(key, ""))

    def analyze(self, fmt, options):
        self.record("analyze", fmt, options)
        return self.text

    def quit(self):
        self.record("quit")
        return self.quit_result

    def run(self, values=None, visible=False):
        return driver.ComDriver().put_fields(
            self.template,
            self.output,
            {"title": "New title", "body": "New body"} if values is None else values,
            visible,
        )

    @property
    def operations(self):
        return [name for name, _, _ in self.calls]


@pytest.fixture
def fake(tmp_path, monkeypatch):
    fake = FakeCom(tmp_path)
    monkeypatch.setattr(driver, "_uncertain", False)
    monkeypatch.setattr(driver, "_runtime", lambda: fake.runtime)
    return fake


def test_duplicate_fields_are_written_by_basename_and_read_by_saved_occurrence(fake):
    result = fake.run(visible=True)
    verification = result["verification"]
    expected = [
        {"field": "title", "occurrence": 0},
        {"field": "body", "occurrence": 0},
        {"field": "title", "occurrence": 1},
    ]
    assert verification["template_fields"] == verification["saved_fields"] == expected
    assert verification["readback"] == [
        {**item, "value": "New title" if item["field"] == "title" else "New body"}
        for item in expected
    ]
    assert verification["contract_version"] == 1
    assert verification["lifecycle"] == LIFECYCLE
    assert verification["output_sha256"] == hashlib.sha256(fake.output.read_bytes()).hexdigest()
    assert verification["template_sha256"] == hashlib.sha256(fake.template.read_bytes()).hexdigest()
    assert result["fields"] == result["replaced"] == ["title", "body"]
    assert result["missing"] == result["remaining_placeholders"] == result["warnings"] == []
    assert result["output_path"] == str(fake.output)
    assert fake.window.Visible is True
    calls = [(name, args) for name, args, _ in fake.calls]
    assert ("dispatch", (driver.PROG_ID,)) in calls
    assert ("mutex_create", (None, False, driver.MUTEX_NAME)) in calls
    assert ("mutex_wait", (123, 0)) in calls
    assert [args for name, args in calls if name == "fields"] == [(0, 0), (0, 0)]
    assert [args for name, args in calls if name == "write"] == [
        ("title", "New title"),
        ("body", "New body"),
    ]
    assert [args for name, args in calls if name == "read"] == [
        ("title{{0}}",),
        ("body{{0}}",),
        ("title{{1}}",),
    ]
    assert [args[0] for name, args in calls if name == "open"] == [
        str(fake.template),
        str(fake.output),
    ]
    assert ("save", (str(fake.output), "HWPX", "")) in calls
    assert fake.operations[-4:] == ["quit", "uninitialize", "release", "handle_close"]


def test_hwp_save_format_and_com_calls_stay_on_calling_queue_thread(fake):
    fake.output = fake.output.with_suffix(".hwp")
    results = []
    thread = threading.Thread(target=lambda: results.append(fake.run()))
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert results[0]["verification"]["lifecycle"] == LIFECYCLE
    assert {tid for _, _, tid in fake.calls} == {thread.ident}
    assert next(args[1] for name, args, _ in fake.calls if name == "save") == "HWP"


@pytest.mark.parametrize("text", ["\n", "first\nsecond", "a\rb\r\nc", "a\t b \n\n"])
def test_put_field_uses_crlf_without_mutating_requested_values(fake, text):
    values = {"body": text}
    report = fake.run(values)
    writes = [args for name, args, _ in fake.calls if name == "write"]
    assert writes == [("body", driver._newline(text).replace("\n", "\r\n"))]
    assert values == {"body": text}
    from api.parsing.hwp_readback import verify_readback

    assert verify_readback(report, values, report["verification"]["template_sha256"],
                           report["verification"]["output_sha256"])["verified"]


def test_lost_linebreak_remains_failure_with_content_free_diagnostics(fake):
    fake.overrides[("body", 0)] = ""
    with pytest.raises(driver.ComDriverError) as caught:
        fake.run({"body": "\n"})
    assert caught.value.code == "saved_value_mismatch"
    assert caught.value.verification_detail["field_index"] == 1
    assert caught.value.verification_detail["expected_linebreaks"] == 1
    assert caught.value.verification_detail["actual_linebreaks"] == 0


def test_missing_and_unmapped_fields_preserve_exact_requested_partition(fake):
    fake.data[("body", 0)] = "Unmapped existing content"
    result = fake.run({"title": "New", "missing": "Not present"})
    assert result["replaced"] == ["title"]
    assert result["missing"] == ["missing"]
    assert result["remaining_placeholders"] == []
    assert result["warnings"]
    assert all(args[0] != "missing" for name, args, _ in fake.calls if name == "write")


@pytest.mark.parametrize("text", ["", " \r\n", "{{todo}}", "prefix [검증필요] suffix"])
def test_saved_residuals_are_unique_base_names(fake, text):
    result = fake.run({"title": text, "body": "Complete"})
    assert result["remaining_placeholders"] == ["title"]
    assert result["warnings"]


def test_empty_template_fields_are_warning_not_fabricated_success(fake):
    fake.names = []
    result = fake.run({"title": "New"})
    assert result["replaced"] == result["fields"] == []
    assert result["missing"] == ["title"]
    assert result["remaining_placeholders"] == []
    assert result["verification"]["template_fields"] == result["verification"]["readback"] == []
    assert result["warnings"]


def test_readback_normalizes_only_newlines_and_one_protocol_terminator(fake):
    fake.overrides = {("title", 0): "a\r\nb\x02", ("title", 1): "a\rb"}
    result = fake.run({"title": "a\nb", "body": "New body"})
    assert result["verification"]["readback"][0]["value"] == "a\r\nb"


@pytest.mark.parametrize("text", ["wrong", "New title ", "new title", "New  title"])
def test_any_saved_occurrence_mismatch_fails(fake, text):
    fake.overrides[("title", 1)] = text
    with pytest.raises(driver.ComDriverError) as exc:
        fake.run()
    assert (exc.value.code, exc.value.stage) == ("saved_value_mismatch", "verify")
    assert fake.operations[-5:] == ["clear", "quit", "uninitialize", "release", "handle_close"]


@pytest.mark.parametrize(
    "names", [["title", "body"], ["title", "body", "other"], ["body", "title", "title"]]
)
def test_saved_inventory_changes_fail(fake, names):
    fake.saved_names = names
    with pytest.raises(driver.ComDriverError, match="saved_fields_mismatch"):
        fake.run()
    assert "read" not in fake.operations
    assert "quit" in fake.operations


@pytest.mark.parametrize(
    "attribute,value,code,stage",
    [
        ("save_result", False, "document_save_failed", "save"),
        ("save_result", None, "document_save_failed", "save"),
        ("open_results", [False, True], "document_open_failed", "open"),
        ("open_results", [True, False], "document_open_failed", "reopen"),
        ("write_result", False, "com_reported_failure", "write"),
        ("write_file", False, "document_hash_failed", "output_hash"),
        ("corrupt_on_second_close", True, "saved_file_changed", "verify"),
        ("mutate_template_on_save", True, "template_changed", "verify"),
    ],
)
def test_failures_never_return_verified_payload(fake, attribute, value, code, stage):
    setattr(fake, attribute, value)
    with pytest.raises(driver.ComDriverError) as exc:
        fake.run()
    assert (exc.value.code, exc.value.stage) == (code, stage)
    assert "quit" in fake.operations
    assert fake.operations[-3:] == ["uninitialize", "release", "handle_close"]


@pytest.mark.parametrize("operation", ["fields", "write", "save", "read", "open", "window"])
def test_native_errors_are_redacted_and_cleanup_runs(fake, operation):
    fake.failures.add(operation)
    with pytest.raises(driver.ComDriverError) as exc:
        fake.run()
    assert "private-path-and-document-secret" not in str(exc.value)
    assert exc.value.stage
    assert "quit" in fake.operations
    assert fake.operations[-3:] == ["uninitialize", "release", "handle_close"]


@pytest.mark.parametrize(
    "operation,cleanup_code",
    [
        ("quit", "quit_failed"),
        ("uninitialize", "uninitialize_failed"),
        ("release", "mutex_release_failed"),
        ("handle_close", "mutex_close_failed"),
    ],
)
def test_cleanup_failure_prevents_success_and_latches_uncertainty(fake, operation, cleanup_code):
    fake.failures.add(operation)
    with pytest.raises(driver.ComDriverError) as exc:
        fake.run()
    assert exc.value.code == "com_cleanup_failed"
    assert cleanup_code in exc.value.cleanup_errors
    assert fake.operations[-3:] == ["uninitialize", "release", "handle_close"]
    assert driver.ComDriver.availability() == {"available": False, "code": "com_state_uncertain"}
    count = len(fake.calls)
    with pytest.raises(driver.ComDriverError, match="com_state_uncertain"):
        fake.run()
    assert len(fake.calls) == count


def test_original_failure_and_all_cleanup_errors_are_retained(fake):
    fake.save_result = False
    fake.failures.update({"clear", "quit", "uninitialize", "release", "handle_close"})
    with pytest.raises(driver.ComDriverError) as exc:
        fake.run()
    assert exc.value.code == "document_save_failed"
    assert exc.value.stage == "save"
    assert exc.value.cleanup_errors == [
        "close_failed",
        "quit_failed",
        "uninitialize_failed",
        "mutex_release_failed",
        "mutex_close_failed",
    ]
    assert exc.value.lifecycle == ["opened", "written"]


@pytest.mark.parametrize("attribute", ["quit_result", "clear_result"])
def test_explicit_false_from_void_cleanup_is_failure(fake, attribute):
    setattr(fake, attribute, False)
    with pytest.raises(driver.ComDriverError):
        fake.run()
    assert "quit" in fake.operations
    assert driver.ComDriver.availability()["available"] is False


@pytest.mark.parametrize(
    "wait,code,owned",
    [
        (258, "worker_busy", False),
        (128, "mutex_abandoned", True),
        (0xFFFFFFFF, "mutex_wait_failed", False),
    ],
)
def test_mutex_is_failfast_and_never_dispatches_when_not_cleanly_acquired(fake, wait, code, owned):
    fake.wait = wait
    with pytest.raises(driver.ComDriverError) as exc:
        fake.run()
    assert exc.value.code == code
    assert "dispatch" not in fake.operations
    assert "initialize" not in fake.operations
    assert ("release" in fake.operations) is owned
    assert fake.operations[-1] == "handle_close"
    if wait == 128:
        assert driver.ComDriver.availability()["available"] is False


@pytest.mark.parametrize("operation,uninitialize", [("initialize", False), ("dispatch", True)])
def test_initialization_and_activation_failures_release_mutex(fake, operation, uninitialize):
    fake.failures.add(operation)
    with pytest.raises(driver.ComDriverError) as exc:
        fake.run()
    assert exc.value.stage == operation
    assert ("uninitialize" in fake.operations) is uninitialize
    assert "quit" not in fake.operations
    assert fake.operations[-2:] == ["release", "handle_close"]


@pytest.mark.parametrize("method", ["inspect", "analyze"])
def test_read_operations_close_without_saving_and_return_occurrences(fake, method):
    original = fake.template.read_bytes()
    result = getattr(driver.ComDriver(), method)(fake.template)
    assert result["fields"] == ["title", "body"]
    assert len(result["field_occurrences"]) == len(result["readback"]) == 3
    assert result["sha256"] == hashlib.sha256(original).hexdigest()
    assert result["lifecycle"] == ["opened", "readback", "closed", "quit"]
    assert "save" not in fake.operations
    assert "write" not in fake.operations
    assert fake.template.read_bytes() == original
    if method == "analyze":
        assert result["text"] == fake.text
        assert next(args for name, args, _ in fake.calls if name == "analyze") == ("UNICODE", "")


def test_analyze_failure_still_closes_and_quits(fake):
    fake.text = None
    with pytest.raises(driver.ComDriverError, match="invalid_document_text"):
        driver.ComDriver().analyze(fake.template)
    assert fake.operations[-5:] == ["clear", "quit", "uninitialize", "release", "handle_close"]


def test_extracted_text_limit_preserves_cleanup(fake):
    fake.text = "x" * 200_001
    with pytest.raises(driver.ComDriverError, match="document_text_too_large"):
        driver.ComDriver().analyze(fake.template)
    assert any(name == "quit" for name, _, _ in fake.calls)


def test_field_readback_limit_preserves_cleanup(fake):
    fake.overrides[("title", 0)] = "x" * 100_001
    with pytest.raises(driver.ComDriverError, match="field_text_too_large"):
        driver.ComDriver().inspect(fake.template)
    assert any(name == "quit" for name, _, _ in fake.calls)
    assert fake.operations[-5:] == ["clear", "quit", "uninitialize", "release", "handle_close"]


@pytest.mark.parametrize(
    "field_list", [123, "title\x02", "title\x02\x02body", "title{{0}}", "\x00"]
)
def test_invalid_field_list_cannot_become_empty_verified_fields(fake, field_list):
    fake.field_list = field_list
    with pytest.raises(driver.ComDriverError, match="invalid_field_list"):
        fake.run()
    assert "save" not in fake.operations


@pytest.mark.parametrize("value", [None, 123, "value\x02extra", "value\x00"])
def test_invalid_readback_is_not_coerced(fake, value):
    fake.overrides[("title", 0)] = value
    with pytest.raises(driver.ComDriverError, match="invalid_field_text"):
        fake.run()


def test_availability_does_not_dispatch_or_initialize_com(fake):
    assert driver.ComDriver.availability() == {
        "available": True,
        "code": "hwp_com_registered_activation_unverified",
    }
    assert fake.calls == []


def test_unavailable_dependency_is_a_safe_status(monkeypatch):
    monkeypatch.setattr(driver, "_uncertain", False)

    def unavailable():
        raise driver.ComDriverError("pywin32_unavailable", "availability")

    monkeypatch.setattr(driver, "_runtime", unavailable)
    assert driver.ComDriver.availability() == {"available": False, "code": "pywin32_unavailable"}


class FakeRegistry:
    HKEY_CLASSES_ROOT = "classes"
    KEY_READ = 0x20019
    KEY_WOW64_64KEY = 0x100
    KEY_WOW64_32KEY = 0x200

    def __init__(self, entries):
        self.entries = entries
        self.accesses = []

    def OpenKey(self, root, path, reserved, access):
        assert root == self.HKEY_CLASSES_ROOT
        assert reserved == 0
        assert access in (
            self.KEY_READ | self.KEY_WOW64_64KEY,
            self.KEY_READ | self.KEY_WOW64_32KEY,
        )
        key = (access & 0x300, path)
        self.accesses.append(key)
        if key not in self.entries:
            raise FileNotFoundError
        return nullcontext(key)

    def QueryValueEx(self, key, name):
        assert name == ""
        return self.entries[key], 1


@pytest.mark.parametrize("view", [FakeRegistry.KEY_WOW64_64KEY, FakeRegistry.KEY_WOW64_32KEY])
@pytest.mark.parametrize("prog_id", driver.PROG_IDS)
def test_registration_reads_both_views_and_versioned_progids(view, prog_id):
    clsid = "{12345678-1234-1234-1234-123456789ABC}"
    registry = FakeRegistry(
        {
            (view, prog_id + r"\CLSID"): clsid,
            (view, "CLSID\\" + clsid + r"\LocalServer32"): '"C:\\Hancom\\Hwp.exe"',
        }
    )
    assert driver._registered_progid(registry) == prog_id
    assert all(access[0] in (0x100, 0x200) for access in registry.accesses)


def test_missing_registration_does_not_claim_hancom_is_not_installed():
    registry = FakeRegistry({})
    with pytest.raises(driver.ComDriverError) as exc:
        driver._registered_progid(registry)
    assert exc.value.code == "hwp_com_registration_missing"
    assert len(registry.accesses) == 2 * len(driver.PROG_IDS)


def test_incomplete_registration_is_not_reported_ready():
    registry = FakeRegistry(
        {(0x200, driver.PROG_ID + r"\CLSID"): "{12345678-1234-1234-1234-123456789ABC}"}
    )
    with pytest.raises(driver.ComDriverError, match="hwp_com_registration_missing"):
        driver._registered_progid(registry)


def test_registry_access_failure_is_distinct_from_missing_registration(monkeypatch):
    registry = FakeRegistry({})

    def denied(*args):
        raise PermissionError("private registry diagnostic")

    monkeypatch.setattr(registry, "OpenKey", denied)
    with pytest.raises(driver.ComDriverError) as exc:
        driver._registered_progid(registry)
    assert exc.value.code == "hwp_registration_unreadable"
    assert "private" not in str(exc.value)


def test_selected_versioned_progid_is_used_for_isolated_dispatch(fake):
    fake.runtime.prog_id = driver.PROG_ID + ".1"
    fake.run()
    assert next(args for name, args, _ in fake.calls if name == "dispatch") == (
        driver.PROG_ID + ".1",
    )


def test_existing_output_is_refused_inside_mutex_before_open(fake):
    fake.output.write_bytes(b"previous writer output")
    with pytest.raises(driver.ComDriverError, match="output_exists"):
        fake.run()
    assert "mutex_wait" in fake.operations
    assert "open" not in fake.operations
    assert "save" not in fake.operations
    assert fake.output.read_bytes() == b"previous writer output"
    assert fake.operations[-4:] == ["quit", "uninitialize", "release", "handle_close"]


def test_output_written_while_waiting_for_mutex_is_preserved(fake):
    def acquired(handle, timeout):
        fake.record("mutex_wait", handle, timeout)
        fake.output.write_bytes(b"writer finished before mutex acquired")
        return 0

    fake.runtime.event.WaitForSingleObject = acquired
    with pytest.raises(driver.ComDriverError, match="output_exists"):
        fake.run()
    assert "open" not in fake.operations
    assert fake.output.read_bytes() == b"writer finished before mutex acquired"


def test_output_is_rechecked_immediately_before_save(fake):
    original = fake.hwp.PutFieldText

    def changed(name, text):
        original(name, text)
        fake.output.write_bytes(b"new file appeared")

    fake.hwp.PutFieldText = changed
    with pytest.raises(driver.ComDriverError, match="output_exists"):
        fake.run()
    assert "save" not in fake.operations
    assert fake.output.read_bytes() == b"new file appeared"


def test_broken_output_symlink_is_refused_even_when_exists_is_false(fake, monkeypatch):
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == fake.output or original(path))
    with pytest.raises(driver.ComDriverError, match="output_exists"):
        fake.run()
    assert "open" not in fake.operations


def test_digest_is_bounded_and_allows_exact_limit(tmp_path, monkeypatch):
    path = tmp_path / "bounded.hwp"
    monkeypatch.setattr(driver, "MAX_DOCUMENT_BYTES", 64)
    path.write_bytes(b"x" * 64)
    assert driver._digest(path, "test_hash") == hashlib.sha256(b"x" * 64).hexdigest()
    path.write_bytes(b"x" * 65)
    with pytest.raises(driver.ComDriverError) as exc:
        driver._digest(path, "test_hash")
    assert (exc.value.code, exc.value.stage) == ("document_too_large", "test_hash")


def test_oversized_template_fails_before_open_but_releases_com(fake, monkeypatch):
    monkeypatch.setattr(driver, "MAX_DOCUMENT_BYTES", 2)
    with pytest.raises(driver.ComDriverError, match="document_too_large"):
        fake.run()
    assert "open" not in fake.operations
    assert fake.operations[-4:] == ["quit", "uninitialize", "release", "handle_close"]
