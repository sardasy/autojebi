"""Load and validate company-owned decision policy YAML."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from api.decision.models import CompanyPolicy


class CompanyPolicyLoadError(ValueError):
    pass


def load_company_policy(path: str | Path) -> CompanyPolicy:
    policy_path = Path(path)
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CompanyPolicyLoadError(f"cannot load company policy: {policy_path}") from exc
    if not isinstance(payload, dict):
        raise CompanyPolicyLoadError("company policy must be a YAML mapping")
    try:
        return CompanyPolicy.model_validate(payload)
    except ValidationError as exc:
        raise CompanyPolicyLoadError(f"invalid company policy: {exc}") from exc
