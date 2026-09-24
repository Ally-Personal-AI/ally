"""Strict non-secret configuration models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ally.security.network import is_loopback_http_url


class InferenceDefaults(BaseModel):
    """Non-secret defaults for selecting a private local inference endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint: str = Field(default="http://127.0.0.1:8080/v1", min_length=1)
    model: str | None = None

    @field_validator("endpoint")
    @classmethod
    def require_private_loopback_endpoint(cls, value: str) -> str:
        if not is_loopback_http_url(value):
            raise ValueError("private inference configuration must use a loopback endpoint")
        return value


class PrivacyDefaults(BaseModel):
    """Hard private-inference boundary with fail-closed legacy parsing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    private_inference_local_only: Literal[True] = True

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_remote_opt_in(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for field in ("allow_remote_inference", "allow_private_context_remote"):
            if field not in data:
                continue
            legacy = data.pop(field)
            if legacy is not False:
                raise ValueError(
                    f"{field} is no longer supported; private Ally inference is local-only"
                )
        return data


class AllyConfig(BaseModel):
    """Versioned Ally configuration document containing no secret values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    inference: InferenceDefaults = Field(default_factory=InferenceDefaults)
    privacy: PrivacyDefaults = Field(default_factory=PrivacyDefaults)
