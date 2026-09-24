from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ally.diagnostics import (
    EvaluationSuiteProfile,
    HardwareProfile,
    PerformanceObservations,
    RuntimeProfile,
)
from ally.runtime_profiles import (
    EvidenceReference,
    InferenceTargetError,
    RuntimeProfileCatalogError,
    ValidatedRuntimeProfile,
    resolve_inference_target,
)


def _profile() -> ValidatedRuntimeProfile:
    return ValidatedRuntimeProfile.model_construct(
        schema_version=2,
        profile_id="a" * 64,
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version="0.1.0.dev0",
        endpoint="http://127.0.0.1:8080/v1",
        model="qualified-model",
        runtime=RuntimeProfile(name="llama.cpp", version="b1234"),
        hardware=HardwareProfile(
            system="Darwin",
            release="25.0",
            machine="arm64",
            processor="arm",
            python_version="3.12.11",
            logical_cpu_count=16,
            total_memory_bytes=128 * 1024**3,
            apple_model="Mac17,1",
            apple_chip="Apple M5 Max",
        ),
        evaluation_suite=EvaluationSuiteProfile(
            core_sha256="1" * 64,
            provider_sha256="2" * 64,
            behavioral_sha256="3" * 64,
        ),
        observations=PerformanceObservations(),
        capability_evidence=EvidenceReference(
            name="capability.json",
            sha256="4" * 64,
        ),
        privacy_evidence=EvidenceReference(
            name="privacy.json",
            sha256="5" * 64,
        ),
        workflow_evidence=EvidenceReference(
            name="workflows.json",
            sha256="6" * 64,
        ),
    )


def test_default_inference_target_resolves_active_validated_profile() -> None:
    target = resolve_inference_target(active_profile_resolver=_profile)

    assert target.source == "validated_profile"
    assert target.endpoint == "http://127.0.0.1:8080/v1"
    assert target.model == "qualified-model"
    assert target.profile_id == "a" * 64
    assert target.runtime_name == "llama.cpp"
    assert target.runtime_version == "b1234"


def test_explicit_development_target_requires_complete_pair() -> None:
    with pytest.raises(InferenceTargetError, match="both endpoint and model"):
        resolve_inference_target(development_model="candidate")

    with pytest.raises(InferenceTargetError, match="both endpoint and model"):
        resolve_inference_target(
            development_endpoint="http://127.0.0.1:9999/v1"
        )


def test_explicit_development_target_is_loopback_only() -> None:
    with pytest.raises(InferenceTargetError, match="loopback target"):
        resolve_inference_target(
            development_endpoint="https://example.com/v1",
            development_model="candidate",
        )


def test_explicit_development_target_does_not_claim_validated_identity() -> None:
    target = resolve_inference_target(
        development_endpoint="http://127.0.0.1:9999/v1",
        development_model="candidate",
    )

    assert target.source == "development_override"
    assert target.endpoint == "http://127.0.0.1:9999/v1"
    assert target.model == "candidate"
    assert target.profile_id is None
    assert target.runtime_name is None
    assert target.runtime_version is None


def test_missing_or_invalid_active_profile_fails_closed() -> None:
    def unavailable() -> ValidatedRuntimeProfile:
        raise RuntimeProfileCatalogError("no active runtime profile is selected")

    with pytest.raises(
        InferenceTargetError,
        match="active validated runtime profile is unavailable or invalid",
    ):
        resolve_inference_target(active_profile_resolver=unavailable)
