"""Typed models for data-minimized external egress."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

EgressDataClass = Literal[
    "public",
    "explicit_outbound",
    "private_internal",
    "secret",
]
EgressDecision = Literal["allow", "require_approval", "deny"]
EgressStatus = Literal["succeeded", "approval_required", "denied", "failed"]


class EgressFieldSpec(BaseModel):
    """Trusted adapter declaration for one possible outbound field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$",
    )
    classification: EgressDataClass
    required: bool = True


class EgressOperationSpec(BaseModel):
    """Trusted field-classification schema for one external operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    fields: tuple[EgressFieldSpec, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def require_unique_field_names(self) -> EgressOperationSpec:
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("egress operation field names must be unique")
        return self


class EgressRequest(BaseModel):
    """Values proposed for one declared external operation.

    Classifications deliberately do not appear here. They come from trusted
    adapter code, not model/user-supplied request values.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    service: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    operation: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    fields: dict[str, JsonValue] = Field(max_length=100)


class EgressFieldManifest(BaseModel):
    """Payload-free field metadata suitable for inspection and audit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$",
    )
    classification: EgressDataClass


class EgressInspection(BaseModel):
    """What would cross the trust boundary, without exposing values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    service: str
    operation: str
    decision: EgressDecision
    fields: tuple[EgressFieldManifest, ...]
    error_class: str | None = Field(default=None, max_length=128)


class EgressExecution(BaseModel):
    """Result of one policy-enforced egress attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    service: str
    operation: str
    decision: EgressDecision
    status: EgressStatus
    started_at: datetime
    finished_at: datetime
    output: JsonValue | None = None
    error_class: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> EgressExecution:
        expected = {
            "succeeded": "allow",
            "failed": "allow",
            "approval_required": "require_approval",
            "denied": "deny",
        }[self.status]
        if self.decision != expected:
            raise ValueError("egress status is inconsistent with policy decision")
        if self.status == "failed" and self.error_class is None:
            raise ValueError("failed egress requires error_class")
        if self.status != "failed" and self.error_class is not None:
            raise ValueError("only failed egress may retain error_class")
        if self.status != "succeeded" and self.output is not None:
            raise ValueError("only successful egress may retain output")
        return self
