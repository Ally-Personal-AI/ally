"""Read-only aggregation of Ally 0.1 release-readiness evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReleaseReadinessReport(BaseModel):
    """Path-free summary of the exact evidence used for a release decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    ally_version: str = Field(min_length=1, max_length=100)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    active_profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workflow_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    machine_acceptance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_production_eligible: bool
    machine_acceptance_qualified: bool

    @property
    def ready_for_tagged_prerelease(self) -> bool:
        return (
            self.candidate_production_eligible
            and self.machine_acceptance_qualified
        )
