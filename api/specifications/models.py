from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    document_id: str = Field(min_length=1, max_length=200)
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=12000)
    locator: str = Field(min_length=1, max_length=500)


class Specification(Strict):
    target: str = Field(min_length=1, max_length=200)
    property: str = Field(min_length=1, max_length=100)
    kind: Literal["numeric", "identifier", "text"]
    operator: Literal["eq", "lt", "le", "gt", "ge", "range", "unknown"] = "unknown"
    value: str | None = Field(default=None, max_length=100)
    lower: str | None = Field(default=None, max_length=100)
    upper: str | None = Field(default=None, max_length=100)
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    unit: str = Field(default="", max_length=40)
    identifier: str = Field(default="", max_length=200)
    conditions: str = Field(default="", max_length=1000)
    mandatory: bool = True
    raw: str = Field(min_length=1, max_length=12000)
    uncertainty: str | None = Field(default=None, max_length=100)
    tolerance: str | None = Field(default=None, max_length=100)
    source: Source

    @field_validator("value", "lower", "upper", "uncertainty", "tolerance")
    @classmethod
    def decimal_string(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                number = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("decimal string required") from exc
            if not number.is_finite() or abs(number.adjusted()) > 30:
                raise ValueError("finite decimal with bounded exponent required")
        return value

    @model_validator(mode="after")
    def valid_shape(self) -> Specification:
        if self.source.end - self.source.start != len(self.source.quote):
            raise ValueError("source span length mismatch")
        if self.uncertainty is not None and Decimal(self.uncertainty) < 0:
            raise ValueError("uncertainty cannot be negative")
        if self.tolerance is not None and (Decimal(self.tolerance) < 0 or self.operator != "eq"):
            raise ValueError("nonnegative tolerance requires an equality target")
        if self.tolerance is not None and self.uncertainty is not None:
            raise ValueError("requirement tolerance and measurement uncertainty must be separate")
        if self.operator == "range":
            if self.lower is None or self.upper is None or Decimal(self.lower) > Decimal(self.upper):
                raise ValueError("ordered bounds required")
        if self.kind == "numeric" and self.operator not in {"range", "unknown"} and self.value is None:
            raise ValueError("numeric value required")
        if self.kind == "identifier" and not self.identifier:
            raise ValueError("identifier required")
        return self


class Correction(Strict):
    version: int = Field(ge=1)
    payload: Specification
    note: str = Field(min_length=1, max_length=2000)


class SearchRequest(Strict):
    requirement_id: str | None = Field(default=None, max_length=100)
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)


class Candidate(Strict):
    """Optional LLM output; source coordinates are resolved on the server."""

    target: str = Field(min_length=1, max_length=200)
    property: str = Field(min_length=1, max_length=100)
    kind: Literal["numeric", "identifier", "text"]
    operator: Literal["eq", "lt", "le", "gt", "ge", "range", "unknown"]
    value: str | None = Field(default=None, max_length=100)
    lower: str | None = Field(default=None, max_length=100)
    upper: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="", max_length=40)
    identifier: str = Field(default="", max_length=200)
    conditions: str = Field(default="", max_length=1000)
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    uncertainty: str | None = Field(default=None, max_length=100)
    tolerance: str | None = Field(default=None, max_length=100)

    @field_validator("value", "lower", "upper", "uncertainty", "tolerance")
    @classmethod
    def decimal_values(cls, value: str | None) -> str | None:
        return Specification.decimal_string(value)

    @model_validator(mode="after")
    def numeric_shape(self) -> Candidate:
        if self.uncertainty is not None and Decimal(self.uncertainty) < 0:
            raise ValueError("uncertainty cannot be negative")
        if self.tolerance is not None and (Decimal(self.tolerance) < 0 or self.operator != "eq"):
            raise ValueError("nonnegative tolerance requires an equality target")
        if self.tolerance is not None and self.uncertainty is not None:
            raise ValueError("requirement tolerance and measurement uncertainty must be separate")
        if self.kind == "numeric" and self.operator not in {"range", "unknown"} and self.value is None:
            raise ValueError("numeric value required")
        if self.operator == "range" and (self.lower is None or self.upper is None or Decimal(self.lower) > Decimal(self.upper)):
            raise ValueError("ordered bounds required")
        if self.kind == "identifier" and not self.identifier:
            raise ValueError("identifier required")
        return self
