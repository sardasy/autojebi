"""Opt-in, offline Node parser with no COM, shell, child processes, or source writes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

from pydantic import ValidationError

from api.parsing.hwp_validation import HwpValidationError, validate_hwp_content
from api.parsing.kordoc import ParsedDocument

RUNTIME = Path(__file__).resolve().parents[2] / "tools" / "kordoc_runtime"
MAX_OUTPUT = 4_000_000


class KordocError(ValueError):
    pass


def enabled() -> bool:
    return os.getenv("WORKSPACE_KORDOC_ENABLED", "false").lower() == "true"


def _capture(command: list[str], content: bytes, *, timeout: float) -> bytes:
    # Do not pass API keys, NODE_OPTIONS, preload hooks, or user npm configuration.
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "LANG") if key in os.environ}
    env.update(KORDOC_OFFLINE="1", NODE_NO_WARNINGS="1")
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=RUNTIME, env=env, shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError:
        raise KordocError("runtime_unavailable") from None
    stdout = bytearray()
    over_limit = threading.Event()

    def drain(stream, limit: int, keep: bool) -> None:
        count = 0
        try:
            while chunk := stream.read(65536):
                count += len(chunk)
                if count > limit:
                    over_limit.set()
                    process.kill()
                    return
                if keep:
                    stdout.extend(chunk)
        finally:
            stream.close()

    def feed() -> None:
        try:
            process.stdin.write(content)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    threads = [threading.Thread(target=drain, args=(process.stdout, MAX_OUTPUT, True)),
               threading.Thread(target=drain, args=(process.stderr, 32768, False)),
               threading.Thread(target=feed)]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise KordocError("parser_timeout") from None
    finally:
        for thread in threads:
            thread.join()
    if over_limit.is_set():
        raise KordocError("output_limit")
    if process.returncode:
        # Error text and stderr from dependencies never escape the adapter.
        raise KordocError("parser_failed")
    return bytes(stdout)


def parse_document(content: bytes, suffix: str, *, timeout: float = 30) -> ParsedDocument:
    if not enabled():
        raise KordocError("kordoc_disabled")
    if suffix.lower() not in {".hwp", ".hwpx"}:
        raise KordocError("unsupported_format")
    try:
        # Keep existing decompression, protected-file, and format checks before the new parser.
        validate_hwp_content(content, suffix)
    except HwpValidationError:
        raise KordocError("source_structure_rejected") from None
    executable = shutil.which(os.getenv("KORDOC_NODE_BIN", "node"))
    if not executable or not (RUNTIME / "node_modules/kordoc/package.json").is_file():
        raise KordocError("runtime_unavailable")
    command = [executable, "--permission", f"--allow-fs-read={RUNTIME}",
               "--max-old-space-size=256", str(RUNTIME / "runner.mjs")]
    raw = _capture(command, content, timeout=timeout)
    try:
        result = ParsedDocument.model_validate(json.loads(raw))
    except (ValueError, UnicodeError, ValidationError):
        raise KordocError("invalid_parser_response") from None
    if result.source_sha256 != hashlib.sha256(content).hexdigest():
        raise KordocError("source_hash_mismatch")
    if result.format != suffix.lower().lstrip("."):
        raise KordocError("source_format_mismatch")
    return result
