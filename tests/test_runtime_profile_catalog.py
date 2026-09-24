from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import ally.runtime_profiles.catalog as catalog_module
from ally import __version__
from ally.config import AllyPaths
from ally.diagnostics import (
    EvaluationSuiteProfile,
    HardwareProfile,
    LocalModelValidationReport,
    RuntimePrivacyChecks,
    RuntimeProfile,
    SyntheticWorkflowCheck,
    SyntheticWorkflowReport,
    build_functional_workflow_report,
    build_runtime_privacy_report,
    write_functional_workflow_report,
    write_runtime_privacy_report,
    write_validation_report,
)
from ally.evals import EvalResult, EvalSummary
from ally.runtime_profiles import (
    RuntimeProfileCatalog,
    RuntimeProfileCatalogError,
    build_validated_runtime_profile,
    resolve_active_runtime_profile,
    write_validated_runtime_profile,
)


def _summary() -> EvalSummary:
    result = EvalResult(
        case_id="synthetic",
        category="provider_response",
        evaluator="synthetic",
        status="passed",
        message="",
        duration_ms=1.0,
    )
    return EvalSummary(
        total=1,
        passed=1,
        failed=0,
        errors=0,
        results=(result,),
    )


def _validation(*, model: str) -> LocalModelValidationReport:
    return LocalModelValidationReport(
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version=__version__,
        endpoint="http://127.0.0.1:8080/v1",
        model=model,
        runtime=RuntimeProfile(name="synthetic-runtime", version="1.0"),
        evaluation_suite=EvaluationSuiteProfile(
            core_sha256="a" * 64,
            provider_sha256="b" * 64,
            behavioral_sha256="c" * 64,
        ),
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
        core=_summary(),
        provider=_summary(),
        behavior=_summary(),
        duration_ms=1000.0,
    )


def _qualified_bundle(
    root: Path,
    *,
    model: str = "synthetic-model",
) -> tuple[Path, Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    validation = write_validation_report(
        _validation(model=model),
        root / "capability.json",
    )
    privacy = build_runtime_privacy_report(
        validation_path=validation,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=RuntimePrivacyChecks(
            inference_with_egress_blocked="pass",
            synthetic_chat="pass",
            synthetic_planning="pass",
            synthetic_memory_proposal="pass",
            synthetic_grounding="pass",
            no_cloud_auth_required="pass",
            no_cloud_fallback_observed="pass",
            no_prompt_telemetry_observed="pass",
            no_unexpected_outbound_connections="pass",
        ),
    )
    privacy_path = write_runtime_privacy_report(
        privacy,
        root / "privacy.json",
    )
    workflow = build_functional_workflow_report(
        validation_path=validation,
        workflow=SyntheticWorkflowReport(
            generated_at=datetime(2026, 9, 24, tzinfo=UTC),
            ally_version=__version__,
            provider="synthetic",
            model=model,
            checks=(
                SyntheticWorkflowCheck(
                    id="conversation.persistence",
                    status="passed",
                    duration_ms=1.0,
                ),
            ),
            duration_ms=1.0,
        ),
    )
    workflow_path = write_functional_workflow_report(
        workflow,
        root / "workflows.json",
    )
    profile = build_validated_runtime_profile(
        validation_path=validation,
        privacy_path=privacy_path,
        workflow_path=workflow_path,
    )
    profile_path = write_validated_runtime_profile(
        profile,
        root / "profile.json",
    )
    return validation, privacy_path, workflow_path, profile_path


def _install(
    catalog: RuntimeProfileCatalog,
    bundle: tuple[Path, Path, Path, Path],
) -> Path:
    validation, privacy, workflows, profile = bundle
    return catalog.install(
        profile_path=profile,
        validation_path=validation,
        privacy_path=privacy,
        workflow_path=workflows,
    )


def test_catalog_installs_lists_and_idempotently_reinstalls(
    tmp_path: Path,
) -> None:
    bundle = _qualified_bundle(tmp_path / "evidence")
    catalog = RuntimeProfileCatalog(tmp_path / "config" / "runtime-profiles")

    first = _install(catalog, bundle)
    second = _install(catalog, bundle)

    assert first == second
    profiles = catalog.list()
    assert len(profiles) == 1
    assert profiles[0].profile_id == first.stem
    assert profiles[0].model == "synthetic-model"


def test_catalog_list_rejects_filename_profile_identity_mismatch(
    tmp_path: Path,
) -> None:
    bundle = _qualified_bundle(tmp_path / "evidence")
    catalog = RuntimeProfileCatalog(tmp_path / "catalog")
    installed = _install(catalog, bundle)
    wrong_path = installed.with_name("f" * 64 + ".json")
    installed.rename(wrong_path)

    with pytest.raises(RuntimeProfileCatalogError, match="filename"):
        catalog.list()


def test_catalog_rejects_profile_with_different_evidence(tmp_path: Path) -> None:
    first = _qualified_bundle(tmp_path / "a", model="model-a")
    second = _qualified_bundle(tmp_path / "b", model="model-b")
    catalog = RuntimeProfileCatalog(tmp_path / "catalog")

    with pytest.raises(RuntimeProfileCatalogError, match="verification"):
        catalog.install(
            profile_path=first[3],
            validation_path=second[0],
            privacy_path=second[1],
            workflow_path=second[2],
        )


def test_selection_is_hash_bound_and_tampering_fails_closed(tmp_path: Path) -> None:
    bundle = _qualified_bundle(tmp_path / "evidence")
    catalog = RuntimeProfileCatalog(tmp_path / "catalog")
    installed = _install(catalog, bundle)
    profile_id = installed.stem

    selection = catalog.select(profile_id)
    assert catalog.active().profile_id == profile_id
    assert selection.profile_sha256

    raw = json.loads(installed.read_text(encoding="utf-8"))
    raw["model"] = "tampered-model"
    installed.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(RuntimeProfileCatalogError):
        catalog.active()


def test_missing_selected_profile_fails_closed(tmp_path: Path) -> None:
    bundle = _qualified_bundle(tmp_path / "evidence")
    catalog = RuntimeProfileCatalog(tmp_path / "catalog")
    installed = _install(catalog, bundle)
    catalog.select(installed.stem)
    installed.unlink()

    with pytest.raises(RuntimeProfileCatalogError, match="not installed"):
        catalog.active()


def test_active_profile_must_be_deselected_before_removal(tmp_path: Path) -> None:
    bundle = _qualified_bundle(tmp_path / "evidence")
    catalog = RuntimeProfileCatalog(tmp_path / "catalog")
    installed = _install(catalog, bundle)
    profile_id = installed.stem
    catalog.select(profile_id)

    with pytest.raises(RuntimeProfileCatalogError, match="deselect"):
        catalog.remove(profile_id)

    assert catalog.deselect() is True
    assert catalog.remove(profile_id) is True
    assert catalog.remove(profile_id) is False
    assert catalog.deselect() is False


def test_catalog_rejects_symlinked_profile_source(tmp_path: Path) -> None:
    bundle = _qualified_bundle(tmp_path / "evidence")
    symlink = tmp_path / "profile-link.json"
    symlink.symlink_to(bundle[3])
    catalog = RuntimeProfileCatalog(tmp_path / "catalog")

    with pytest.raises(RuntimeProfileCatalogError, match="symlink"):
        catalog.install(
            profile_path=symlink,
            validation_path=bundle[0],
            privacy_path=bundle[1],
            workflow_path=bundle[2],
        )


def test_active_selection_contains_no_local_paths(tmp_path: Path) -> None:
    private_root = tmp_path / "PRIVATE-CATALOG-PATH"
    bundle = _qualified_bundle(tmp_path / "evidence")
    catalog = RuntimeProfileCatalog(private_root)
    installed = _install(catalog, bundle)
    catalog.select(installed.stem)

    rendered = catalog.selection_path.read_text(encoding="utf-8")

    assert "PRIVATE-CATALOG-PATH" not in rendered
    assert str(tmp_path) not in rendered
    assert installed.stem in rendered


def test_default_active_resolver_uses_ally_config_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = AllyPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr(catalog_module, "default_paths", lambda: paths)
    bundle = _qualified_bundle(tmp_path / "evidence")
    catalog = catalog_module.default_runtime_profile_catalog()
    installed = _install(catalog, bundle)
    catalog.select(installed.stem)

    resolved = resolve_active_runtime_profile()

    assert resolved.profile_id == installed.stem
    assert resolved.model == "synthetic-model"



def test_catalog_wraps_unavailable_root_without_raw_path_leakage(
    tmp_path: Path,
) -> None:
    bundle = _qualified_bundle(tmp_path / "evidence")
    blocked_root = tmp_path / "PRIVATE-BLOCKED-CATALOG"
    blocked_root.write_text("not a directory", encoding="utf-8")
    catalog = RuntimeProfileCatalog(blocked_root)

    with pytest.raises(
        RuntimeProfileCatalogError,
        match="catalog is unavailable",
    ) as error:
        _install(catalog, bundle)

    assert "PRIVATE-BLOCKED-CATALOG" not in str(error.value)
    assert str(tmp_path) not in str(error.value)
