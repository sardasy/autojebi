"""Worker HTTP/queue boundaries only: fake driver, no HWP installation or COM calls."""

from __future__ import annotations

import asyncio
import gc
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.hwp_worker.app import create_app
from api.hwp_worker.paths import AllowedPaths, PathViolation

TOKEN = "test-only-hwp-worker-token-32chars"
HEADERS = {"X-Agent-Token": TOKEN}
PUT = "/document/put-fields"


class FakeDriver:
    def __init__(self, *, block: bool = False, available: bool = True) -> None:
        self.block = block
        self.available = available
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls: list[dict[str, Any]] = []
        self.availability_calls = 0
        self.active = 0
        self.max_active = 0
        self.guard = threading.Lock()

    def availability(self) -> dict:
        self.availability_calls += 1
        return {"available": self.available, "installed": self.available}

    def _call(self, kind: str, path: Path, **extra: Any) -> None:
        with self.guard:
            self.calls.append(
                {
                    "kind": kind,
                    "path": path,
                    "thread": threading.get_ident(),
                    "thread_name": threading.current_thread().name,
                    **extra,
                }
            )

    def put_fields(self, template: Path, output: Path, values: dict, visible: bool) -> dict:
        self._call("put", output, template=template, values=values, visible=visible)
        with self.guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.started.set()
            if self.block and not self.release.wait(5):
                raise RuntimeError("fake driver was not released")
            return {
                "output_path": str(output),
                "replaced": list(values),
                "missing": [],
                "remaining_placeholders": [],
                "fields": list(values),
            }
        finally:
            with self.guard:
                self.active -= 1

    def inspect(self, path: Path) -> dict:
        self._call("inspect", path)
        return {"fields": ["company_name"]}

    def analyze(self, path: Path) -> dict:
        self._call("analyze", path)
        return {"text": "test document"}


@pytest.fixture
def paths(tmp_path: Path) -> AllowedPaths:
    roots = [tmp_path / name for name in ("templates", "sources", "outputs")]
    for root in roots:
        root.mkdir()
    (roots[0] / "template.hwp").write_bytes(b"fake template")
    (roots[1] / "source.hwpx").write_bytes(b"fake source")
    return AllowedPaths(*roots)


@pytest.fixture
def driver() -> FakeDriver:
    return FakeDriver()


@pytest.fixture
def client(paths: AllowedPaths, driver: FakeDriver):
    app = create_app(token=TOKEN, paths=paths, driver=driver, timeout_s=2)
    with TestClient(app) as client:
        yield client
    app.state.queue._thread.join(1)
    assert not app.state.queue._thread.is_alive()
    assert app.state.queue.state() == {"running": False, "queued": 0, "accepting": False}


def put_body(**changes: Any) -> dict:
    return {
        "template_path": "template.hwp",
        "output_path": "result.hwp",
        "values": {"company_name": "Example"},
        **changes,
    }


@pytest.mark.parametrize("token", ["", "x" * 31, " " * 32, " " + "x" * 31 + " "])
def test_token_requires_at_least_32_nonpadding_characters(paths, driver, token):
    with pytest.raises(ValueError, match="32"):
        create_app(token=token, paths=paths, driver=driver)


def test_missing_environment_token_fails_closed(paths, driver, monkeypatch):
    monkeypatch.delenv("HWP_AGENT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="32"):
        create_app(paths=paths, driver=driver)


def test_exactly_32_character_token_accepted(paths, driver):
    token = "x" * 32
    with TestClient(create_app(token=token, paths=paths, driver=driver)) as client:
        assert client.get("/health", headers={"X-Agent-Token": token}).status_code == 200


@pytest.mark.parametrize(
    "headers", [{}, {"X-Agent-Token": "wrong"}, {"X-Agent-Token": TOKEN + "x"}]
)
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/health", None),
        ("POST", PUT, put_body()),
        ("POST", "/document/fields", {"path": "template.hwp"}),
        ("POST", "/document/analyze-file", {"path": "source.hwpx"}),
    ],
)
def test_every_endpoint_requires_token(client, driver, method, path, body, headers):
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"
    assert driver.calls == [] and driver.availability_calls == 0


@pytest.mark.parametrize("endpoint", [PUT, "/document/fields", "/document/analyze-file"])
def test_unauthenticated_malformed_json_still_returns_401(client, driver, endpoint):
    response = client.post(endpoint, content=b"{", headers={"Content-Type": "application/json"})
    assert response.status_code == 401
    assert not driver.calls


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"])
@pytest.mark.parametrize("headers", [{}, HEADERS])
def test_openapi_and_documentation_are_disabled(client, path, headers):
    assert client.get(path, headers=headers).status_code == (404 if headers else 401)


@pytest.mark.parametrize("streamed", [False, True], ids=["content-length", "chunked"])
@pytest.mark.parametrize("headers,status", [(HEADERS, 413), ({}, 401)])
def test_oversized_request_is_rejected_without_queueing(
    client,
    driver,
    monkeypatch,
    streamed,
    headers,
    status,
):
    body = json.dumps(put_body()).encode()
    body += b" " * (4_000_001 - len(body))
    content = (
        (body[start : start + 65_536] for start in range(0, len(body), 65_536))
        if streamed
        else body
    )
    owner = client.app.state.queue
    before = owner.state()
    submissions = []
    submit = owner.submit

    def observe(operation):
        submissions.append(operation)
        return submit(operation)

    monkeypatch.setattr(owner, "submit", observe)
    response = client.post(
        PUT,
        headers={**headers, "Content-Type": "application/json"},
        content=content,
    )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == (
        "request_too_large" if status == 413 else "unauthorized"
    )
    if streamed:
        assert "content-length" not in response.request.headers
    assert submissions == [] and driver.calls == []
    assert owner.state() == before == {"running": False, "queued": 0, "accepting": True}
    assert client.post(PUT, headers=HEADERS, json=put_body()).status_code == 200
    assert len(submissions) == len(driver.calls) == 1
    assert client.get("/health", headers=HEADERS).json()["queue"] == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("template_path", "../templates/template.hwp"),
        ("output_path", "../outputs/result.hwp"),
        ("output_path", "nested/../result.hwp"),
        ("output_path", "//server/share/result.hwp"),
        ("output_path", "\\\\server\\share\\result.hwp"),
        ("output_path", "bad\x00.hwp"),
        ("output_path", "result.exe"),
        ("output_path", "missing-parent/result.hwp"),
    ],
)
def test_unsafe_put_paths_never_reach_driver(client, paths, driver, field, value):
    response = client.post(PUT, headers=HEADERS, json=put_body(**{field: value}))
    assert response.status_code == 422
    assert not driver.calls
    assert driver.availability_calls == 0
    assert not (paths.output_root / ".hwp-active.json").exists()


@pytest.mark.parametrize("field", ["template_path", "output_path"])
def test_absolute_outside_paths_rejected(client, paths, driver, tmp_path, field):
    outside = tmp_path / "outside.hwp"
    if field == "template_path":
        outside.write_bytes(b"outside")
    response = client.post(PUT, headers=HEADERS, json=put_body(**{field: str(outside)}))
    assert response.status_code == 422 and not driver.calls
    assert response.json()["detail"]["code"] == "path_outside_root"


@pytest.mark.parametrize("path", ["result.hwp:payload.hwp", "file:stream.hwpx"])
def test_relative_alternate_data_stream_output_rejected(client, driver, path):
    response = client.post(PUT, headers=HEADERS, json=put_body(output_path=path))
    assert response.status_code == 422
    assert not driver.calls


def test_existing_output_is_not_overwritten(client, paths, driver):
    output = paths.output_root / "result.hwp"
    output.write_bytes(b"keep original")
    response = client.post(PUT, headers=HEADERS, json=put_body())
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "output_exists"
    assert output.read_bytes() == b"keep original" and not driver.calls


@pytest.mark.parametrize(
    "endpoint,path",
    [
        ("/document/fields", "../sources/source.hwpx"),
        ("/document/analyze-file", "../templates/template.hwp"),
    ],
)
def test_read_operations_cannot_cross_roots(client, paths, driver, endpoint, path):
    assert client.post(endpoint, headers=HEADERS, json={"path": path}).status_code == 422
    assert not driver.calls
    assert driver.availability_calls == 0
    assert not (paths.output_root / ".hwp-active.json").exists()


@pytest.mark.parametrize("kind", ["template", "source", "output", "parent"])
def test_symlink_paths_rejected(client, paths, driver, tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "target.hwp"
    target.write_bytes(b"keep outside")
    if kind == "parent":
        link = paths.output_root / "linked"
        destination = outside
    else:
        root = {
            "template": paths.template_root,
            "source": paths.source_root,
            "output": paths.output_root,
        }[kind]
        link = root / "linked.hwp"
        destination = target
    try:
        link.symlink_to(destination, target_is_directory=kind == "parent")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314 or exc.errno in {1, 13, 38, 95}:
            pytest.skip("symlink creation not permitted on this test host")
        raise
    if kind == "source":
        response = client.post("/document/analyze-file", headers=HEADERS, json={"path": str(link)})
    else:
        changes = (
            {"template_path": str(link)}
            if kind == "template"
            else {
                "output_path": str(link / "result.hwp" if kind == "parent" else link),
            }
        )
        response = client.post(PUT, headers=HEADERS, json=put_body(**changes))
    assert response.status_code == 422 and not driver.calls
    assert response.json()["detail"]["code"] == "linked_path"
    assert target.read_bytes() == b"keep outside"


def test_windows_reparse_point_rejected_even_without_symlink_privilege(paths, monkeypatch):
    linked = paths.output_root / "junction"
    linked.mkdir()
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if path == linked:
            return SimpleNamespace(st_mode=0, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(PathViolation, match="linked_path"):
        paths.resolve(str(linked / "result.hwp"), "output")


def test_saved_mismatch_exposes_only_structural_diagnostics(client, driver, monkeypatch):
    from api.hwp_worker.com_driver import ComDriverError

    def fail(*args):
        error = ComDriverError("saved_value_mismatch", "verify")
        error.verification_detail = {"field_index": 2, "expected_linebreaks": 1, "actual_linebreaks": 0}
        raise error

    monkeypatch.setattr(driver, "put_fields", fail)
    response = client.post(PUT, headers=HEADERS, json=put_body(values={"company_name": "private-source-text"}))
    assert response.status_code == 502
    assert response.json()["detail"]["verification_detail"] == {
        "field_index": 2, "expected_linebreaks": 1, "actual_linebreaks": 0,
    }
    assert "private-source-text" not in response.text
    assert "company_name" not in response.text


@pytest.mark.parametrize(
    "values",
    [
        {"first\x02second": "value"},
        {"company_name": "first\x02second"},
        {"company_name{{0}}": "value"},
        {"company_name{{1}}": "value"},
        {"company_name{{-1}}": "value"},
        {"company_name}}": "value"},
        {"bad\x00name": "value"},
        {"company_name": "bad\x00value"},
        {" ": "value"},
    ],
)
def test_field_delimiter_and_direct_index_injection_rejected(client, driver, values):
    response = client.post(PUT, headers=HEADERS, json=put_body(values=values))
    assert response.status_code == 422 and not driver.calls


def test_all_document_operations_use_one_owner_thread(client, paths, driver):
    responses = [
        client.post(PUT, headers=HEADERS, json=put_body()),
        client.post("/document/fields", headers=HEADERS, json={"path": "template.hwp"}),
        client.post("/document/analyze-file", headers=HEADERS, json={"path": "source.hwpx"}),
    ]
    assert all(response.status_code == 200 for response in responses)
    assert [call["kind"] for call in driver.calls] == ["put", "inspect", "analyze"]
    assert len({call["thread"] for call in driver.calls}) == 1
    assert driver.calls[0]["thread"] != threading.get_ident()
    assert driver.calls[0]["template"] == paths.template_root / "template.hwp"
    assert driver.calls[0]["path"] == paths.output_root / "result.hwp"


def test_simultaneous_put_requests_are_serial_on_same_owner_thread(paths, monkeypatch):
    driver = FakeDriver(block=True)
    app = create_app(token=TOKEN, paths=paths, driver=driver, timeout_s=3)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        queued = threading.Event()
        submit = app.state.queue.submit
        count = []

        def observe(operation):
            future = submit(operation)
            count.append(future)
            if len(count) == 2:
                queued.set()
            return future

        monkeypatch.setattr(app.state.queue, "submit", observe)
        try:
            first = pool.submit(
                client.post, PUT, headers=HEADERS, json=put_body(output_path="one.hwp")
            )
            assert driver.started.wait(2)
            second = pool.submit(
                client.post, PUT, headers=HEADERS, json=put_body(output_path="two.hwp")
            )
            assert queued.wait(2)
            assert len(driver.calls) == 1
            assert app.state.queue.state()["queued"] == 1
        finally:
            driver.release.set()
        assert first.result(timeout=3).status_code == 200
        assert second.result(timeout=3).status_code == 200
    assert driver.max_active == 1
    assert [call["path"].name for call in driver.calls] == ["one.hwp", "two.hwp"]
    assert len({call["thread"] for call in driver.calls}) == 1


def test_timeout_cancels_queued_but_running_is_uncertain_without_reexecution(paths, monkeypatch):
    driver = FakeDriver(block=True)
    app = create_app(token=TOKEN, paths=paths, driver=driver, timeout_s=0.3)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        submitted = []
        submit = app.state.queue.submit

        def observe(operation):
            future = submit(operation)
            submitted.append(future)
            return future

        monkeypatch.setattr(app.state.queue, "submit", observe)
        try:
            running = pool.submit(
                client.post, PUT, headers=HEADERS, json=put_body(output_path="one.hwp")
            )
            assert driver.started.wait(2)
            waiting = pool.submit(
                client.post, PUT, headers=HEADERS, json=put_body(output_path="two.hwp")
            )
            first, second = running.result(timeout=3), waiting.result(timeout=3)
            assert first.status_code == 504
            assert second.status_code in {503, 504}
            assert first.json()["detail"]["code"] == "operation_uncertain"
            assert first.json()["detail"]["retry_safe"] is False
            assert second.json()["detail"]["code"] in {"queue_timeout", "queue_cancelled"}
            assert second.json()["detail"]["retry_safe"] is True
            assert not submitted[0].cancelled() and submitted[1].cancelled()
            health = client.get("/health", headers=HEADERS).json()
            assert health["queue"]["running"] and not health["generation_verified"]
            marker = paths.output_root / ".hwp-active.json"
            assert json.loads(marker.read_bytes())["state"] == "failed"
            assert health["recovery_required"] and not health["ok"]
            assert not health["accepting"]
        finally:
            driver.release.set()
        from api.hwp_worker.recovery import RecoveryRequired
        with pytest.raises(RecoveryRequired):
            submitted[0].result(timeout=2)
        # Late success cannot unlock subsequent work.
        assert (
            client.post(
                "/document/fields", headers=HEADERS, json={"path": "template.hwp"}
            ).status_code
            == 503
        )
        assert [call["kind"] for call in driver.calls] == ["put"]
        assert driver.max_active == 1
        assert (paths.output_root / ".hwp-active.json").exists()


@pytest.mark.parametrize("available", [False, True])
def test_health_reports_installation_without_generation_proof(paths, available):
    driver = FakeDriver(available=available)
    with TestClient(create_app(token=TOKEN, paths=paths, driver=driver)) as client:
        response = client.get("/health", headers=HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is available and body["installation"]["available"] is available
        assert body["generation_verified"] is False
        assert driver.calls == []
        assert body["queue"] == {"running": False, "queued": 0, "accepting": True}


def test_driver_exception_response_is_sanitized(client, driver, monkeypatch):
    def fail(*args):
        raise RuntimeError("SECRET document content and private path")

    monkeypatch.setattr(driver, "put_fields", fail)
    response = client.post(PUT, headers=HEADERS, json=put_body())
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "hwp_operation_failed"
    assert "SECRET" not in response.text


@pytest.mark.parametrize(
    "method,endpoint,body",
    [
        ("put_fields", PUT, put_body()),
        ("inspect", "/document/fields", {"path": "template.hwp"}),
        ("analyze", "/document/analyze-file", {"path": "source.hwpx"}),
    ],
)
@pytest.mark.parametrize("structured", [False, True], ids=["unexpected-error", "com-error"])
def test_com_failure_blocks_all_endpoints_after_new_app_instance(
    paths,
    monkeypatch,
    method,
    endpoint,
    body,
    structured,
):
    from api.hwp_worker.com_driver import ComDriverError

    driver = FakeDriver()
    marker = paths.output_root / ".hwp-active.json"
    attempts = []

    def fail(*args):
        attempts.append(1)
        assert json.loads(marker.read_bytes())["state"] == "running"
        if structured:
            raise ComDriverError("operation_failed", "save")
        raise RuntimeError("SECRET COM failure")

    monkeypatch.setattr(driver, method, fail)
    with TestClient(create_app(token=TOKEN, paths=paths, driver=driver)) as client:
        first = client.post(endpoint, headers=HEADERS, json=body)
        assert first.status_code == 502 and "SECRET" not in first.text
        assert attempts == [1]
        saved = marker.read_bytes()
        assert json.loads(saved)["state"] == "failed"
        again = client.post(endpoint, headers=HEADERS, json=body)
        assert again.status_code == 503
        assert again.json()["detail"]["code"] == "recovery_required"
        assert again.json()["detail"]["retry_safe"] is False
        assert attempts == [1] and marker.read_bytes() == saved

    replacement = FakeDriver()
    with TestClient(create_app(token=TOKEN, paths=paths, driver=replacement)) as restarted:
        health = restarted.get("/health", headers=HEADERS).json()
        assert health["installation"]["available"] is True
        assert health["ok"] is False and health["recovery_required"] is True
        assert health["generation_verified"] is False
        assert health["queue"] == {"running": False, "queued": 0, "accepting": True}
        for target, payload in (
            (PUT, put_body()),
            ("/document/fields", {"path": "template.hwp"}),
            ("/document/analyze-file", {"path": "source.hwpx"}),
        ):
            response = restarted.post(target, headers=HEADERS, json=payload)
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "recovery_required"
            assert response.json()["detail"]["retry_safe"] is False
        assert replacement.calls == [] and marker.read_bytes() == saved
        assert restarted.get("/health", headers=HEADERS).json()["queue"] == health["queue"]


@pytest.mark.parametrize(
    "endpoint,body",
    [
        (PUT, put_body()),
        ("/document/fields", {"path": "template.hwp"}),
        ("/document/analyze-file", {"path": "source.hwpx"}),
    ],
)
def test_unavailable_installation_does_not_create_marker(paths, endpoint, body):
    driver = FakeDriver(available=False)
    marker = paths.output_root / ".hwp-active.json"
    with TestClient(create_app(token=TOKEN, paths=paths, driver=driver)) as client:
        response = client.post(endpoint, headers=HEADERS, json=body)
        assert response.status_code == 502
        assert response.json()["detail"]["stage"] == "availability"
        assert driver.calls == [] and not marker.exists()
        health = client.get("/health", headers=HEADERS).json()
        assert not health["ok"] and not health["recovery_required"]
        assert health["queue"] == {"running": False, "queued": 0, "accepting": True}
        driver.available = True
        assert client.post(endpoint, headers=HEADERS, json=body).status_code == 200
        assert len(driver.calls) == 1 and not marker.exists()


def test_late_driver_exception_after_timeout_is_consumed(paths, monkeypatch, caplog):
    driver = FakeDriver()
    app = create_app(token=TOKEN, paths=paths, driver=driver, timeout_s=0.05)
    release = threading.Event()

    def fail_late(*args):
        if not release.wait(3):
            raise RuntimeError("fake driver was not released")
        raise RuntimeError("SECRET late COM exception")

    monkeypatch.setattr(driver, "put_fields", fail_late)
    with TestClient(app) as client:
        submitted = []
        submit = app.state.queue.submit

        def observe(operation):
            future = submit(operation)
            submitted.append(future)
            return future

        monkeypatch.setattr(app.state.queue, "submit", observe)
        try:
            response = client.post(PUT, headers=HEADERS, json=put_body())
            assert response.status_code == 504
            assert response.json()["detail"]["code"] == "operation_uncertain"
        finally:
            release.set()
        with pytest.raises(RuntimeError, match="SECRET"):
            submitted[0].result(timeout=2)

        async def flush_callbacks():
            for _ in range(5):
                await asyncio.sleep(0)
            gc.collect()

        client.portal.call(flush_callbacks)
        assert "SECRET" not in caplog.text
        assert "exception was never retrieved" not in caplog.text
        marker = paths.output_root / ".hwp-active.json"
        assert json.loads(marker.read_bytes())["state"] == "failed"
        response = client.post("/document/fields", headers=HEADERS, json={"path": "template.hwp"})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "recovery_required"
        assert driver.calls == []
        health = client.get("/health", headers=HEADERS).json()
        assert not health["ok"] and health["recovery_required"]


def test_lifespan_closes_queue_and_rejects_later_submissions(paths, driver):
    app = create_app(token=TOKEN, paths=paths, driver=driver)
    with TestClient(app) as client:
        assert client.get("/health", headers=HEADERS).status_code == 200
        owner = app.state.queue
    assert owner.state()["accepting"] is False
    with pytest.raises(RuntimeError, match="queue_closed"):
        owner.submit(lambda: {})
    owner._thread.join(1)
    assert not owner._thread.is_alive()


def test_cli_binds_only_loopback_and_single_process(monkeypatch):
    from api.hwp_worker import __main__ as cli

    calls = []
    sentinel = object()
    monkeypatch.setattr("sys.argv", ["hwp_worker", "--port", "8123"])
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr(cli, "create_app", lambda: sentinel)
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    cli.main()
    assert calls == [
        (sentinel, {"host": "127.0.0.1", "port": 8123, "workers": 1, "access_log": False})
    ]
