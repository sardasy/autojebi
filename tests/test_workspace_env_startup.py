"""CLI environment loading without a database, subprocess, or HWP operation."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.workspace import supervisor, worker


@pytest.mark.parametrize("entrypoint", ["worker", "supervisor"])
@pytest.mark.parametrize("env_file_exists", [False, True])
@pytest.mark.parametrize("explicit_token", [False, True])
def test_entrypoint_loads_env_before_runtime_and_preserves_explicit_values(
    monkeypatch, tmp_path, entrypoint, env_file_exists, explicit_token
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.delenv("HWP_AGENT_TOKEN", raising=False)
    monkeypatch.delenv("WORKSPACE_STARTUP_TEST_VALUE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://explicit.invalid/startup_test")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path / "explicit-data"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "explicit-uploads"))
    if explicit_token:
        monkeypatch.setenv("HWP_AGENT_TOKEN", "explicit-test-placeholder")
    if env_file_exists:
        (tmp_path / ".env").write_text(
            "HWP_AGENT_TOKEN=file-test-placeholder\n"
            "WORKSPACE_STARTUP_TEST_VALUE=from-file\n"
            "DATABASE_URL=postgresql://file.invalid/startup_test\n"
            "WORKSPACE_DATA_DIR=file-data\n"
            "UPLOAD_DIR=file-uploads\n",
            encoding="utf-8",
        )

    def assert_environment() -> None:
        expected_token = (
            "explicit-test-placeholder"
            if explicit_token
            else "file-test-placeholder"
            if env_file_exists
            else None
        )
        assert os.getenv("HWP_AGENT_TOKEN") == expected_token
        assert os.getenv("WORKSPACE_STARTUP_TEST_VALUE") == (
            "from-file" if env_file_exists else None
        )
        assert os.environ["DATABASE_URL"] == "postgresql://explicit.invalid/startup_test"
        assert os.environ["WORKSPACE_DATA_DIR"] == str(tmp_path / "explicit-data")
        assert os.environ["UPLOAD_DIR"] == str(tmp_path / "explicit-uploads")

    if entrypoint == "worker":
        engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def get_engine():
            assert_environment()
            return engine

        health = Mock()
        run_once = Mock(return_value=False)
        monkeypatch.setattr(sys, "argv", ["worker", "--once"])
        monkeypatch.setattr(worker, "get_engine", get_engine)
        monkeypatch.setattr(worker.receipts, "RuntimeHealth", lambda: health)
        monkeypatch.setattr(worker, "run_once", run_once)
        worker.main()
        run_once.assert_called_once_with(engine, health)
        health.start.assert_called_once_with()
        health.stop.assert_called_once_with()
    else:
        monkeypatch.setattr(sys, "argv", ["supervisor"])
        supervise = Mock(side_effect=lambda stop: assert_environment())
        monkeypatch.setattr(supervisor.signal, "signal", Mock())
        monkeypatch.setattr(supervisor, "supervise", supervise)
        supervisor.main()
        supervise.assert_called_once()

    assert_environment()
