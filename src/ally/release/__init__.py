"""Release/update trust policy for Ally artifacts."""

from ally.release.update_trust import (
    ReleaseIdentity,
    ReleaseMetadata,
    UpdateDecision,
    UpdateTrustError,
    compare_release_metadata,
    parse_codesign_identity,
    require_signing_identity,
)

__all__ = [
    "ReleaseIdentity",
    "ReleaseMetadata",
    "UpdateDecision",
    "UpdateTrustError",
    "compare_release_metadata",
    "parse_codesign_identity",
    "require_signing_identity",
]
