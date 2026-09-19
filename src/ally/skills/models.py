"""Skill manifest, installation, and execution domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

SkillConfigType = Literal["string", "integer", "number", "boolean"]
SkillExecutionMode = Literal["python_subprocess_v1"]
SkillExecutionStatus = Literal[
    "succeeded",
    "failed",
    "timed_out",
    "output_limit",
    "protocol_error",
]
_ERROR_CLASS_PATTERN = r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$"


class SkillConfigField(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: SkillConfigType
    description: str = Field(min_length=1)
    required: bool = False
    secret: bool = False


class SkillManifest(BaseModel):
    """Validated contents of a skill.toml file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(min_length=1)
    version: str = Field(
        min_length=1,
        pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$",
    )
    description: str = Field(min_length=1)
    entrypoint: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$",
    )
    execution: SkillExecutionMode | None = None
    required_tools: tuple[str, ...] = ()
    optional_tools: tuple[str, ...] = ()
    config: dict[str, SkillConfigField] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_declarations(self) -> SkillManifest:
        required = set(self.required_tools)
        optional = set(self.optional_tools)
        overlap = required & optional
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"tools cannot be both required and optional: {names}")
        if len(required) != len(self.required_tools):
            raise ValueError("required_tools contains duplicates")
        if len(optional) != len(self.optional_tools):
            raise ValueError("optional_tools contains duplicates")

        if self.execution is not None and self.entrypoint is None:
            raise ValueError("executable skill requires an entrypoint")
        if self.execution == "python_subprocess_v1":
            if self.required_tools or self.optional_tools:
                raise ValueError(
                    "python_subprocess_v1 does not expose Ally tools"
                )
            if self.config:
                raise ValueError(
                    "python_subprocess_v1 does not expose skill config"
                )
        return self


class SkillPackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    root: str
    manifest: SkillManifest


class SkillInstallation(BaseModel):
    """Metadata for one locally installed skill package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    skill_id: str
    version: str
    source_uri: str
    installed_at: datetime
    enabled: bool = False


class SkillWorkerRequest(BaseModel):
    """JSON sent to the isolated skill worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal[1] = 1
    input: dict[str, JsonValue] = Field(default_factory=dict)


class SkillWorkerResponse(BaseModel):
    """Strict JSON emitted by the isolated skill worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal[1] = 1
    ok: bool
    result: JsonValue | None = None
    error_class: str | None = Field(
        default=None,
        pattern=_ERROR_CLASS_PATTERN,
    )

    @model_validator(mode="after")
    def validate_outcome(self) -> SkillWorkerResponse:
        if self.ok and self.error_class is not None:
            raise ValueError("successful skill response cannot have error_class")
        if not self.ok and self.error_class is None:
            raise ValueError("failed skill response requires error_class")
        if not self.ok and self.result is not None:
            raise ValueError("failed skill response cannot retain result")
        return self


class SkillExecutionResult(BaseModel):
    """Validated result returned to Ally after one child-process execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill_id: str
    version: str
    status: SkillExecutionStatus
    result: JsonValue | None = None
    error_class: str | None = Field(
        default=None,
        pattern=_ERROR_CLASS_PATTERN,
    )
    exit_code: int | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    audit_id: UUID | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("skill execution timestamps must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_execution_outcome(self) -> SkillExecutionResult:
        if self.finished_at < self.started_at:
            raise ValueError("skill execution cannot finish before it starts")
        if self.status == "succeeded" and self.error_class is not None:
            raise ValueError("successful skill execution cannot have error_class")
        if self.status != "succeeded" and self.error_class is None:
            raise ValueError("failed skill execution requires error_class")
        if self.status != "succeeded" and self.result is not None:
            raise ValueError("failed skill execution cannot retain result")
        return self


class SkillExecutionAuditRecord(BaseModel):
    """Payload-free durable metadata for one child-process execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    installation_id: UUID
    skill_id: str
    version: str
    status: SkillExecutionStatus
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    exit_code: int | None = None
    error_class: str | None = Field(
        default=None,
        pattern=_ERROR_CLASS_PATTERN,
    )

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_audit_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("skill audit timestamps must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_audit_outcome(self) -> SkillExecutionAuditRecord:
        if self.finished_at < self.started_at:
            raise ValueError("skill audit cannot finish before it starts")
        if self.status == "succeeded" and self.error_class is not None:
            raise ValueError("successful skill audit cannot have error_class")
        if self.status != "succeeded" and self.error_class is None:
            raise ValueError("failed skill audit requires error_class")
        return self
