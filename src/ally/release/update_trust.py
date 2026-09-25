"""Deterministic policy for accepting a macOS application update candidate."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SOURCE_REVISION_RE = re.compile(r"[0-9a-f]{40}")
_TEAM_IDENTIFIER_RE = re.compile(r"[A-Z0-9]{10}")


class UpdateTrustError(RuntimeError):
    """Raised when a release or update candidate violates Ally's trust policy."""


@dataclass(frozen=True)
class ReleaseMetadata:
    bundle_identifier: str
    ally_version: str
    short_version: tuple[int, int, int]
    build_version: int
    bridge_protocol_version: int
    database_schema_version: int
    source_revision: str | None


@dataclass(frozen=True)
class ReleaseIdentity:
    bundle_identifier: str
    team_identifier: str


@dataclass(frozen=True)
class UpdateDecision:
    current_build_version: int
    candidate_build_version: int
    current_ally_version: str
    candidate_ally_version: str
    current_database_schema_version: int
    candidate_database_schema_version: int
    candidate_source_revision: str
    requires_pre_migration_backup: bool


def compare_release_metadata(
    current: ReleaseMetadata,
    candidate: ReleaseMetadata,
    *,
    expected_bundle_identifier: str,
) -> UpdateDecision:
    """Require a forward-only, self-identifying update candidate."""

    if current.bundle_identifier != expected_bundle_identifier:
        raise UpdateTrustError("installed application identity is not trusted")
    if candidate.bundle_identifier != expected_bundle_identifier:
        raise UpdateTrustError("candidate application identity is not trusted")
    if current.build_version < 1 or candidate.build_version < 1:
        raise UpdateTrustError("release build version is invalid")
    if candidate.build_version <= current.build_version:
        raise UpdateTrustError("rollback or same-build replacement is rejected")
    if candidate.short_version < current.short_version:
        raise UpdateTrustError("candidate semantic version moves backward")
    if candidate.bridge_protocol_version < current.bridge_protocol_version:
        raise UpdateTrustError("candidate bridge protocol moves backward")
    if candidate.database_schema_version < current.database_schema_version:
        raise UpdateTrustError("candidate database schema support moves backward")
    revision = candidate.source_revision
    if revision is None or _SOURCE_REVISION_RE.fullmatch(revision) is None:
        raise UpdateTrustError("candidate source revision is not release-grade")

    return UpdateDecision(
        current_build_version=current.build_version,
        candidate_build_version=candidate.build_version,
        current_ally_version=current.ally_version,
        candidate_ally_version=candidate.ally_version,
        current_database_schema_version=current.database_schema_version,
        candidate_database_schema_version=candidate.database_schema_version,
        candidate_source_revision=revision,
        requires_pre_migration_backup=(
            candidate.database_schema_version > current.database_schema_version
        ),
    )


def parse_codesign_identity(output: str) -> ReleaseIdentity:
    """Extract the signed bundle/team identity from codesign detail output."""

    identifier: str | None = None
    team_identifier: str | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("Identifier="):
            value = line.removeprefix("Identifier=").strip()
            if identifier is not None and identifier != value:
                raise UpdateTrustError("code signature reports conflicting identifiers")
            identifier = value
        elif line.startswith("TeamIdentifier="):
            value = line.removeprefix("TeamIdentifier=").strip()
            if team_identifier is not None and team_identifier != value:
                raise UpdateTrustError("code signature reports conflicting team identifiers")
            team_identifier = value

    if not identifier:
        raise UpdateTrustError("code signature bundle identifier is unavailable")
    if team_identifier is None or _TEAM_IDENTIFIER_RE.fullmatch(team_identifier) is None:
        raise UpdateTrustError("code signature team identifier is unavailable")
    return ReleaseIdentity(
        bundle_identifier=identifier,
        team_identifier=team_identifier,
    )


def require_signing_identity(
    identity: ReleaseIdentity,
    *,
    expected_bundle_identifier: str,
    expected_team_identifier: str,
) -> None:
    if _TEAM_IDENTIFIER_RE.fullmatch(expected_team_identifier) is None:
        raise UpdateTrustError("expected Developer ID team identifier is invalid")
    if identity.bundle_identifier != expected_bundle_identifier:
        raise UpdateTrustError("signed bundle identifier does not match Ally")
    if identity.team_identifier != expected_team_identifier:
        raise UpdateTrustError("signed Developer ID team does not match Ally")
