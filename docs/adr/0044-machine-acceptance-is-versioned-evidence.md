# ADR 0044: Dedicated-machine acceptance is versioned, payload-free evidence

## Status

Accepted

## Context

Ally's remaining 0.1 blockers are primarily empirical rather than architectural.
They include real macOS Keychain behavior, recovery, signed-app background
execution, notification identity, Developer ID/notarization, update
preparation, application replacement, and integrated daily-use behavior.

A prose checklist is necessary for the procedure but is a weak release
boundary. It can become stale, can be copied between machines, and does not bind
the observations to the exact Ally build or selected validated runtime profile.

The evidence must also remain safe to retain. Machine acceptance must not create
a new store for personal prompts, credentials, file paths, packet payloads, or
other private data.

## Decision

Represent dedicated-machine acceptance as a strict, versioned, immutable,
payload-free artifact.

The artifact is bound to:

- exact Ally version;
- full Git source revision;
- exact hardware/OS profile;
- active validated runtime profile ID; and
- the SHA-256 from Ally's hash-bound active-profile selection.

The empirical gate set is fixed in schema v1. Each gate records only
`pass`, `fail`, or `not_run`.

A report is release-qualified only when every gate passes. Verification must
re-check the current Ally version, source revision supplied by the operator,
hardware profile, and active-profile hash binding.

Synthetic CI may exercise artifact mechanics but must never be treated as real
machine acceptance.

## Consequences

- release acceptance becomes inspectable and reproducible;
- stale evidence fails after relevant environment/profile changes;
- failed acceptance can be retained without granting release eligibility;
- personal data is not needed in acceptance evidence;
- the artifact cannot bypass the underlying runbook or manufacture platform
  observations;
- after a failed gate is fixed, new evidence is created instead of overwriting
  prior evidence; and
- a future release-readiness aggregate can depend on this artifact without
  weakening candidate capability/privacy/workflow requirements.
