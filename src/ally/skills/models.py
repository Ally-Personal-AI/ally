"""Skill manifest and installation domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SkillConfigType = Literal["string", "integer", "number", "boolean"]


class SkillConfigField(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: SkillConfigType
    description: str = Field(min_length=1)
    required: bool = False
    secret: bool = False


class SkillManifest(BaseModel):
    """Validated contents of a skill.toml file."""

    model_config = ConfigDict(frozen=True)

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
    required_tools: tuple[str, ...] = ()
    optional_tools: tuple[str, ...] = ()
    config: dict[str, SkillConfigField] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_tool_declarations(self) -> SkillManifest:
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
        return self


class SkillPackage(BaseModel):
    model_config = ConfigDict(frozen=True)

    root: str
    manifest: SkillManifest


class SkillInstallation(BaseModel):
    """Metadata for one locally installed skill package."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    skill_id: str
    version: str
    source_uri: str
    installed_at: datetime
    enabled: bool = True
