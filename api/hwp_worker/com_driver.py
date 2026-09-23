"""Desktop Hancom COM adapter; call operations on the worker's dedicated thread.

Desktop reference (not WebHWP): hancom-io/devcenter-archive,
hwp-automation/HwpAutomation_2504.pdf, pp. 13-20, 24, 28-29, 58-59.
PutFieldText and Clear are void methods. Clear(1) closes/discards the current
document. GetFieldText uses zero-based {{n}} selectors and CRLF paragraphs.

availability checks dependencies and both registry views read-only; it never
activates Hancom or changes registration. Activation, security prompts, save filters, and actual COM
process isolation must be verified on the deployment desktop. No security module
is registered, no message-box policy is changed, and no process is killed.
An abandoned mutex or failed cleanup latches this process unavailable until an
operator checks the desktop and restarts the worker. HTTP timeout cannot cancel
a hung COM call; the queue must keep that operation exclusive until it returns.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from api.hwp_worker.errors import ComDriverError
from api.hwp_worker.field_text import normalize, wire_text
from api.hwp_worker.use_cases import (
    field_names,
    generate_document,
    inspect_document,
    remaining_fields,
)

# Compatibility imports used by existing verification helpers.
_remaining = remaining_fields
_newline = normalize

PROG_ID = "HWPFrame.HwpObject"
PROG_IDS = (PROG_ID, PROG_ID + ".1", PROG_ID + ".2")
MUTEX_NAME = r"Global\autojebi.HwpComDriver.v1"
MAX_DOCUMENT_BYTES = 50_000_000
_uncertain = False


def _registered_progid(registry: Any) -> str:
    unreadable = False
    for prog_id in PROG_IDS:
        for view in (registry.KEY_WOW64_64KEY, registry.KEY_WOW64_32KEY):
            try:
                access = registry.KEY_READ | view
                with registry.OpenKey(
                    registry.HKEY_CLASSES_ROOT, prog_id + r"\CLSID", 0, access
                ) as key:
                    clsid, _ = registry.QueryValueEx(key, "")
                if not isinstance(clsid, str):
                    continue
                try:
                    UUID(clsid.strip("{}"))
                except ValueError:
                    continue
                with registry.OpenKey(
                    registry.HKEY_CLASSES_ROOT, "CLSID\\" + clsid + r"\LocalServer32", 0, access
                ) as key:
                    server, _ = registry.QueryValueEx(key, "")
                if isinstance(server, str) and server.strip():
                    return prog_id
            except FileNotFoundError:
                continue
            except OSError:
                unreadable = True
    code = "hwp_registration_unreadable" if unreadable else "hwp_com_registration_missing"
    raise ComDriverError(code, "availability")


def _runtime() -> SimpleNamespace:
    if sys.platform != "win32":
        raise ComDriverError("windows_required", "availability")
    try:
        import winreg

        import pythoncom
        import win32api
        import win32com.client
        import win32event
    except (ImportError, OSError):
        raise ComDriverError("pywin32_unavailable", "availability") from None
    return SimpleNamespace(
        com=pythoncom,
        api=win32api,
        event=win32event,
        client=win32com.client,
        prog_id=_registered_progid(winreg),
    )


def _call(stage: str, operation: Callable[..., Any], *args: Any) -> Any:
    from api.hwp_worker.progress import stage as report_stage

    name = getattr(operation, "__name__", "")
    if name == "Run" and args and isinstance(args[0], str):
        name = args[0]
    report_stage(stage, name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", name) else None)
    try:
        return operation(*args)
    except Exception:
        raise ComDriverError("com_call_failed", stage) from None


def _success(value: Any) -> bool:
    return type(value) in (bool, int) and value in (True, -1)


def _void(stage: str, operation: Callable[..., Any], *args: Any) -> None:
    value = _call(stage, operation, *args)
    if value is not None and not _success(value):
        raise ComDriverError("com_reported_failure", stage)


def _digest(path: Path, stage: str) -> str:
    try:
        digest, size = hashlib.sha256(), 0
        with path.open("rb") as stream:
            while chunk := stream.read(min(1024 * 1024, MAX_DOCUMENT_BYTES + 1 - size)):
                size += len(chunk)
                if size > MAX_DOCUMENT_BYTES:
                    raise ComDriverError("document_too_large", stage)
                digest.update(chunk)
        if not size:
            raise OSError("empty document")
        return digest.hexdigest()
    except OSError:
        raise ComDriverError("document_hash_failed", stage) from None


def _refuse_existing_output(output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise ComDriverError("output_exists", "output")


@dataclass
class _Session:
    """Native adapter implementing DocumentSession on the Worker's COM object."""

    hwp: Any = None
    opened: bool = False
    cleanup_needed: bool = False
    lifecycle: list[str] = field(default_factory=list)

    @staticmethod
    def fingerprint(path: Path, stage: str) -> str:
        return _digest(path, stage)

    @staticmethod
    def require_new_output(output: Path) -> None:
        _refuse_existing_output(output)

    def write(self, name: str, value: str) -> None:
        _void("write", self.hwp.PutFieldText, name, wire_text(value))

    def save(self, output: Path, output_format: str) -> None:
        if not _success(_call("save", self.hwp.SaveAs, str(output), output_format, "")):
            raise ComDriverError("document_save_failed", "save")

    def text(self) -> str:
        text = _call("analyze", self.hwp.GetTextFile, "UNICODE", "")
        if not isinstance(text, str):
            raise ComDriverError("invalid_document_text", "analyze")
        if len(text) > 200_000:
            raise ComDriverError("document_text_too_large", "analyze")
        return text

    def page_images(self, output: Path) -> list[dict[str, Any]]:
        from api.hwp_worker.page_images import render

        return render(self.hwp, output)

    def open(self, path: Path, *, reopen: bool = False) -> None:
        stage = "reopen" if reopen else "open"
        self.cleanup_needed = True  # A failed Open can leave a partially loaded document.
        if not _success(_call(stage, self.hwp.Open, str(path), "", "suspendpassword:true")):
            raise ComDriverError("document_open_failed", stage)
        self.opened = True
        self.lifecycle.append("reopened" if reopen else "opened")

    def close(self) -> None:
        _void("close", self.hwp.Clear, 1)
        self.opened = False
        self.cleanup_needed = False
        self.lifecycle.append("closed")

    def enumerate(self) -> list[dict[str, Any]]:
        raw = _call("enumerate", self.hwp.GetFieldList, 0, 0)
        if not isinstance(raw, str):
            raise ComDriverError("invalid_field_list", "enumerate")
        if not raw:
            return []
        # Desktop reference p. 19 explicitly excludes a trailing separator.
        names = raw.split("\x02")
        if len(names) > 10000 or any(
            not name.strip() or len(name) > 200 or any(token in name for token in ("\x00", "{{", "}}"))
            for name in names
        ):
            raise ComDriverError("invalid_field_list", "enumerate")
        counts: Counter[str] = Counter()
        fields = []
        for name in names:
            fields.append({"field": name, "occurrence": counts[name]})
            counts[name] += 1
        return fields

    def read(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        total = 0
        for item in fields:
            selector = item["field"] + "{{" + str(item["occurrence"]) + "}}"
            value = _call("readback", self.hwp.GetFieldText, selector)
            if not isinstance(value, str):
                raise ComDriverError("invalid_field_text", "readback")
            # A single requested field may carry its protocol terminator, never a second value.
            value = value.removesuffix("\x02")
            if "\x02" in value or "\x00" in value:
                raise ComDriverError("invalid_field_text", "readback")
            total += len(value)
            if len(value) > 100_000 or total > 1_000_000:
                raise ComDriverError("field_text_too_large", "readback")
            result.append({**item, "value": value})
        self.lifecycle.append("readback")
        return result


@contextmanager
def _operation(visible: bool) -> Iterator[_Session]:
    global _uncertain
    if _uncertain:
        raise ComDriverError("com_state_uncertain", "mutex")
    runtime = _runtime()
    session = _Session()
    mutex, owned, initialized = None, False, False
    failure: ComDriverError | None = None
    cleanup_errors: list[str] = []
    stage = "mutex"
    try:
        mutex = _call(stage, runtime.event.CreateMutex, None, False, MUTEX_NAME)
        wait = _call(stage, runtime.event.WaitForSingleObject, mutex, 0)
        owned = wait in (runtime.event.WAIT_OBJECT_0, runtime.event.WAIT_ABANDONED)
        if wait == runtime.event.WAIT_ABANDONED:
            _uncertain = True
            raise ComDriverError("mutex_abandoned", stage)
        if wait == runtime.event.WAIT_TIMEOUT:
            raise ComDriverError("worker_busy", stage)
        if not owned:
            raise ComDriverError("mutex_wait_failed", stage)
        stage = "initialize"
        _call(stage, runtime.com.CoInitializeEx, runtime.com.COINIT_APARTMENTTHREADED)
        initialized = True
        stage = "dispatch"
        session.hwp = _call(stage, runtime.client.DispatchEx, runtime.prog_id)
        stage = "visibility"
        _call(stage, setattr, session.hwp.XHwpWindows.Item(0), "Visible", visible)
        yield session
    except ComDriverError as exc:
        from api.hwp_worker.progress import failure as report_failure
        report_failure(exc.stage)
        failure = exc
    except Exception:
        failure = ComDriverError("com_call_failed", stage)
    finally:
        if session.hwp is not None:
            if session.opened or session.cleanup_needed:
                try:
                    session.close()
                except Exception:
                    cleanup_errors.append("close_failed")
            try:
                _void("quit", session.hwp.Quit)
                session.lifecycle.append("quit")
            except Exception:
                cleanup_errors.append("quit_failed")
            session.hwp = None
        if initialized:
            try:
                runtime.com.CoUninitialize()
            except Exception:
                cleanup_errors.append("uninitialize_failed")
        if owned:
            try:
                runtime.event.ReleaseMutex(mutex)
            except Exception:
                cleanup_errors.append("mutex_release_failed")
        if mutex is not None:
            try:
                runtime.api.CloseHandle(mutex)
            except Exception:
                cleanup_errors.append("mutex_close_failed")
        if cleanup_errors:
            _uncertain = True
    if failure or cleanup_errors:
        failure = failure or ComDriverError("com_cleanup_failed", "cleanup")
        failure.cleanup_errors = cleanup_errors
        failure.lifecycle = list(session.lifecycle)
        raise failure from None


class ComDriver:
    @staticmethod
    def availability() -> dict:
        if _uncertain:
            return {"available": False, "code": "com_state_uncertain"}
        try:
            _runtime()
        except ComDriverError as exc:
            return {"available": False, "code": exc.code}
        return {"available": True, "code": "hwp_com_registered_activation_unverified"}

    def put_fields(
        self, template: Path, output: Path, values: dict[str, str], visible: bool,
        *, render_pages: bool = False,
    ) -> dict:
        output_format = {".hwp": "HWP", ".hwpx": "HWPX"}.get(output.suffix.lower())
        if output_format is None:
            raise ComDriverError("unsupported_output_format", "input")
        if any(
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(value, str)
            or any(token in name for token in ("\x00", "\x02", "{{", "}}"))
            or any(token in value for token in ("\x00", "\x02"))
            for name, value in values.items()
        ):
            raise ComDriverError("invalid_field_input", "input")
        with _operation(visible) as session:
            result = generate_document(session, template, output, values, render_pages=render_pages)
        return result

    def inspect(self, path: Path, *, visible: bool = False) -> dict:
        return self._inspect(path, extract_text=False, visible=visible)

    def analyze(self, path: Path) -> dict:
        return self._inspect(path, extract_text=True)

    def _inspect(self, path: Path, *, extract_text: bool, visible: bool = False) -> dict:
        with _operation(visible) as session:
            inspection = inspect_document(session, path)
            checksum, fields = inspection.sha256, inspection.fields
            readback = session.read(fields)
            result = {
                "path": str(path),
                "sha256": checksum,
                "fields": field_names(fields),
                "field_occurrences": fields,
                "readback": readback,
                "remaining_placeholders": _remaining(readback),
                "lifecycle": session.lifecycle,
            }
            if extract_text:
                result["text"] = session.text()
            session.close()
            if _digest(path, "source_hash") != checksum:
                raise ComDriverError("source_changed", "verify")
        return result
