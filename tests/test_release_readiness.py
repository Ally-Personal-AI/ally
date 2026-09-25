from __future__ import annotations

from ally.release.readiness import ReleaseReadinessReport


def _report(
    *,
    candidate: bool = True,
    machine: bool = True,
) -> ReleaseReadinessReport:
    return ReleaseReadinessReport(
        ally_version="0.1.0.dev0",
        source_revision="a" * 40,
        active_profile_id="b" * 64,
        active_profile_sha256="c" * 64,
        capability_evidence_sha256="d" * 64,
        privacy_evidence_sha256="e" * 64,
        workflow_evidence_sha256="f" * 64,
        machine_acceptance_sha256="0" * 64,
        candidate_production_eligible=candidate,
        machine_acceptance_qualified=machine,
    )


def test_release_readiness_requires_candidate_and_machine_acceptance() -> None:
    assert _report().ready_for_tagged_prerelease is True
    assert _report(candidate=False).ready_for_tagged_prerelease is False
    assert _report(machine=False).ready_for_tagged_prerelease is False
