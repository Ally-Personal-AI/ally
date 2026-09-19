"""Strict non-secret configuration models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InferenceDefaults(BaseModel):
    """Non-secret defaults for selecting a local inference endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint: str = Field(default="http://127.0.0.1:8080/v1", min_length=1)
    model: str | None = None


class PrivacyDefaults(BaseModel):
    """Safe defaults; explicit commands may still require stronger opt-in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    allow_remote_inference: bool = False
    allow_private_context_remote: bool = False


class AllyConfig(BaseModel):
    """Versioned Ally configuration document containing no secret values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    inference: InferenceDefaults = Field(default_factory=InferenceDefaults)
    privacy: PrivacyDefaults = Field(default_factory=PrivacyDefaults)
