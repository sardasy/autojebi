"""Explicit opt-in: writes a new real Hancom file, never overwrites a template."""

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from api.services.hwp_agent_client import HwpAgentClient
from api.workspace.hwp_readback import verify_readback
from api.workspace.hwp_validation import read_hwp_output, validate_hwp_content


@pytest.mark.skipif(os.getenv("HWP_LIVE_SMOKE") != "true", reason="real Hancom smoke is opt-in")
def test_real_worker_saved_values():
    token = os.getenv("HWP_AGENT_TOKEN", "")
    assert len(token.strip()) >= 32, "Worker token is required"
    template = Path(os.environ["HWP_LIVE_TEMPLATE"]).resolve(strict=True)
    values = json.loads(Path(os.environ["HWP_LIVE_VALUES_PATH"]).read_text(encoding="utf-8-sig"))
    assert isinstance(values, dict) and values, "Nonempty field mapping is required"
    output_root = Path(os.environ["HWP_OUTPUT_ROOT"]).resolve(strict=True)
    output = output_root / f"live-smoke-{uuid.uuid4().hex}{template.suffix.lower()}"
    client = HwpAgentClient(token=token, retries=1, timeout_s=120)
    assert client.health(), "Worker health failed; not a successful integration test"
    before = hashlib.sha256(template.read_bytes()).hexdigest()
    response = client.put_fields(
        template_path=str(template), output_path=str(output), values=values, visible=True,
    )
    content = read_hwp_output(output)
    validate_hwp_content(content, output.suffix)
    verification = verify_readback(response.raw, values, before, hashlib.sha256(content).hexdigest())
    assert verification and verification["verified"], "Saved-field evidence is required"
    assert not response.missing, "Requested fields missing from actual template"
    assert not response.remaining_placeholders, "Saved file still contains unfilled fields"
    assert hashlib.sha256(template.read_bytes()).hexdigest() == before
    # Keep the file and evidence for the operator's separate layout/page review.
    output.with_suffix(output.suffix + ".verification.json").write_text(
        json.dumps({"output_path": str(output), "verification": verification,
                    "worker": response.raw, "layout_review": "pending"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
