"""Deterministic data-classification policy for external egress."""

from __future__ import annotations

from ally.egress.models import EgressDecision, EgressRequest


class DefaultEgressPolicy:
    """Decide whether declared data may cross the Ally trust boundary."""

    def decide(self, request: EgressRequest, *, approved: bool) -> EgressDecision:
        classifications = {field.classification for field in request.fields}

        if classifications & {"private_internal", "secret"}:
            return "deny"
        if "explicit_outbound" in classifications and not approved:
            return "require_approval"
        return "allow"
