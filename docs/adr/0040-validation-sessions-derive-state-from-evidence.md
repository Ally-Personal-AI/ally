# ADR 0040: Validation sessions derive state from evidence

**Status:** Accepted

## Context

Ally's first-machine workflow spans readiness, capability/behavior evaluation,
functional workflow qualification, runtime privacy qualification, and creation
of a validated runtime profile.

Each stage already has its own strict evidence boundary. Coordinating those
steps only through a runbook creates avoidable operator bookkeeping and makes
interrupted/rebooted validation sessions harder to resume.

A mutable checklist would be worse: stale "passed" flags could survive after an
artifact was replaced, corrupted, or invalidated.

## Decision

Ally introduces an immutable validation-session manifest that records only:

- session identity;
- creation time and Ally version;
- a safe candidate label; and
- the relative leaf filenames planned for capability, workflow, privacy, and
  validated-profile artifacts.

The manifest stores no stage pass/fail state.

Every session refresh recomputes stage state from:

- live read-only machine readiness;
- strict loading of the current evidence files;
- source-binding verification for workflow/privacy artifacts; and
- full validated-runtime-profile verification against all exact evidence.

Derived stage states are `pending`, `passed`, `failed`, `inconsistent`,
or `blocked`.

The next action is deterministic from those live states. Privacy can never be
auto-passed by the session layer; the explicit runtime-privacy artifact remains
required.

## Consequences

Validation can resume after process exits, reboots, or operator interruption
without persisting redundant authority state.

Replacing or tampering with an artifact immediately changes the derived session
state on the next refresh.

Session status is useful to future UI, automation, and operator tooling, but it
does not weaken or supersede any evidence qualification rule.
