"""Resolve production inference through validated active runtime profiles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ally.runtime_profiles.catalog import (
    RuntimeProfileCatalogError,
    resolve_active_runtime_profile,
)
from ally.runtime_profiles.models import ValidatedRuntimeProfile
from ally.security.network import is_loopback_http_url

InferenceTargetSource = Literal["validated_profile", "development_override"]


class InferenceTargetError(ValueError):
    """Raised when no trustworthy inference target can be resolved."""


class ResolvedInferenceTarget(BaseModel):
    """One explicit, loopback-only target for private Ally inference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: InferenceTargetSource
    endpoint: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=300)
    profile_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    runtime_name: str | None = Field(default=None, min_length=1, max_length=100)
    runtime_version: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_target(self) -> ResolvedInferenceTarget:
        if not is_loopback_http_url(self.endpoint):
            raise ValueError("private inference targets must use a loopback endpoint")
        if self.source == "validated_profile":
            if (
                self.profile_id is None
                or self.runtime_name is None
                or self.runtime_version is None
            ):
                raise ValueError(
                    "validated inference targets require profile and runtime identity"
                )
        elif any(
            value is not None
            for value in (
                self.profile_id,
                self.runtime_name,
                self.runtime_version,
            )
        ):
            raise ValueError(
                "development inference targets must not claim validated profile identity"
            )
        return self


def resolve_inference_target(
    *,
    development_endpoint: str | None = None,
    development_model: str | None = None,
    active_profile_resolver: Callable[
        [], ValidatedRuntimeProfile
    ] = resolve_active_runtime_profile,
) -> ResolvedInferenceTarget:
    """Resolve active validated inference or an explicit development override."""

    has_endpoint = development_endpoint is not None
    has_model = development_model is not None
    if has_endpoint != has_model:
        raise InferenceTargetError(
            "development inference requires both endpoint and model"
        )

    if has_endpoint and has_model:
        try:
            return ResolvedInferenceTarget(
                source="development_override",
                endpoint=development_endpoint,
                model=development_model,
            )
        except ValueError as exc:
            raise InferenceTargetError(
                "development inference override must be a valid loopback target"
            ) from exc

    try:
        profile = active_profile_resolver()
    except RuntimeProfileCatalogError as exc:
        raise InferenceTargetError(
            f"active validated runtime profile is unavailable or invalid: {exc}"
        ) from exc

    try:
        return ResolvedInferenceTarget(
            source="validated_profile",
            endpoint=profile.endpoint,
            model=profile.model,
            profile_id=profile.profile_id,
            runtime_name=profile.runtime.name,
            runtime_version=profile.runtime.version,
        )
    except ValueError as exc:
        raise InferenceTargetError(
            "active validated runtime profile cannot be used for private inference"
        ) from exc
