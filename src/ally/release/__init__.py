"""Release/update trust policy for Ally artifacts."""

from ally.release.update_preparation import (
    PreMigrationBackupEvidence,
    UpdatePreparationError,
    UpdatePreparationRecord,
    prepare_update,
)
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
    "PreMigrationBackupEvidence",
    "ReleaseIdentity",
    "ReleaseMetadata",
    "UpdateDecision",
    "UpdatePreparationError",
    "UpdatePreparationRecord",
    "UpdateTrustError",
    "compare_release_metadata",
    "parse_codesign_identity",
    "prepare_update",
    "require_signing_identity",
]
