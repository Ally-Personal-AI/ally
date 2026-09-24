# ADR 0036: Runtime privacy qualification is separate fail-closed evidence

**Status:** Accepted

## Context

Ally Core restricts private inference requests to the local trust domain, but a
local model runtime is independent software. It may still initiate network
connections, require cloud authorization, emit telemetry, or transparently
delegate inference elsewhere.

Model-quality evidence cannot establish those properties.

## Decision

Runtime privacy qualification is a separate immutable artifact from
local-model capability validation.

The privacy artifact references one exact local-model validation artifact by
SHA-256 and copies its runtime/model/hardware identity. It records a reviewed
isolation mode, network-observation method, and explicit results for the
required no-egress/privacy checks.

Every check defaults to `not_run`. Qualification is fail-closed and requires:

- a successful source local-model validation;
- the same Ally version for the source and privacy evidence;
- non-unverified isolation;
- a non-empty network-observation mechanism; and
- every required privacy check to pass.

A privacy report never overwrites prior evidence.

## Consequences

Capability and privacy remain independently inspectable. A model can be capable
but privacy-unqualified, or private but functionally unsuitable; neither state
is sufficient for the production default.

V1 records operator-observed evidence rather than pretending Ally can enforce
egress for an arbitrary third-party runtime before that runtime is selected.

The first-machine runbook uses host-offline validation as the simplest
runtime-independent acceptance method. Stronger process-specific enforcement
may be added after runtime selection or through a future bundled macOS
component using supported platform controls.
