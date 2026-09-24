# ADR 0039: Production runtime selection uses validated runtime profiles

**Status:** Accepted

## Context

Ally can already produce three independently verified evidence artifacts for a
candidate runtime/model:

1. capability and behavioral validation;
2. runtime privacy qualification; and
3. functional workflow qualification.

Those artifacts prove eligibility, but future daily-use composition, desktop UI,
and model routing still need a stable Ally-owned object representing the exact
runtime/model that is approved for use.

Allowing production code to fall back to arbitrary endpoint/model strings would
bypass the evidence chain and make qualification advisory rather than
authoritative.

## Decision

Ally defines an immutable, versioned `ValidatedRuntimeProfile` as the bridge
from qualification evidence into future runtime selection.

A profile can be created only when the exact candidate evidence set is
production-eligible. The profile contains only non-secret operational metadata
needed for runtime composition:

- deterministic profile ID;
- Ally version;
- loopback inference endpoint;
- model identifier;
- runtime/model provenance and artifact fingerprints;
- hardware profile;
- frozen evaluation fingerprints;
- recorded performance observations; and
- path-free SHA-256 references to the exact capability, privacy, and functional
  workflow evidence artifacts.

The profile ID is deterministically derived from the three evidence digests
plus every copied operational metadata field. The creation timestamp is
excluded. This makes metadata tampering self-invalidating even before a profile
is installed or selected.

Profiles are immutable and never overwritten. Verification recomputes all three
evidence digests, re-runs candidate qualification, and confirms every copied
runtime/model/hardware/evaluation/performance field against the source
capability evidence.

## Consequences

Future production selection, UI, service composition, and model routing should
consume validated runtime profiles rather than arbitrary endpoint/model pairs.

A profile is not a runtime launcher and does not claim the process is currently
healthy. It is evidence-backed authorization that an exact runtime/model
configuration is eligible to be selected.

Profile artifacts contain no credentials, prompt/model content, personal state,
or local evidence directory paths.
