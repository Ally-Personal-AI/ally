"""Deterministic data-classification policy for external egress."""

from __future__ import annotations

from collections.abc import Sequence

from ally.egress.models import EgressDecision, EgressFieldManifest


class DefaultEgressPolicy:
    """Decide whether trusted-classified data may cross the Ally trust boundary."""

    def decide(
        self,
        fields: Sequence[EgressFieldManifest],
        *,
        approved: bool,
    ) -> EgressDecision:
        classifications = {field.classification for field in fields}

        if classifications & {"private_internal", "secret"}:
            return "deny"
        if "explicit_outbound" in classifications and not approved:
            return "require_approval"
        return "allow"
