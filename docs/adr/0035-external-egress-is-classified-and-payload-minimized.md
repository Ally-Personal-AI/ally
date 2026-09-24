# ADR 0035: External egress is classified and payload-minimized

**Status:** Accepted

## Context

Ally will eventually need external services such as web search, email,
calendars, public APIs, and devices. Those integrations must not become a second
path for exporting private model context after ADR 0034 prohibited external
inference of private Ally intelligence.

Allowing each integration to build arbitrary network payloads would make data
minimization unenforceable and difficult to audit.

## Decision

Ally defines a separate controlled-egress domain.

A reviewed adapter owns a typed operation schema declaring the only accepted
field names and a fixed classification for each field. Request callers supply
values but cannot supply or override classifications.

The default egress policy:

- allows `public` fields;
- requires explicit approval for `explicit_outbound` fields;
- denies `private_internal` fields;
- denies `secret` fields.

A request containing any denied field is denied as a whole. Unknown fields,
unknown operations, missing required fields, and service mismatches fail before
external execution.

Credentials are not normal egress fields. Future adapters must resolve secret
references at the trusted adapter edge.

All egress attempts use a payload-free audit record containing only destination,
operation, decision/status, approval state, field names/classifications,
timestamps, and safe bounded error classes.

Network-capable external actions must also remain behind Ally's existing
deterministic tool/action policy. The egress policy governs data eligibility; it
does not replace action authorization.

Source-level architecture tests confine common network transport imports to
`ally.models.providers` and `ally.egress`.

## Consequences

Models cannot make private data externally eligible merely by labeling it
public. New integrations must declare their data contract in reviewed code.

Operational audit can answer what categories and field names left Ally without
creating a second copy of the sensitive payload.

This is an application architecture boundary, not a hardened OS network
sandbox. Runtime/skill isolation and the local-model no-egress requirement
remain separate defense layers.

The egress system cannot be used as an external private-inference path; ADR 0034
continues to govern model inference.
