# ADR 0042: Daily private inference resolves the active validated runtime profile

**Status:** Accepted

## Context

Ally already separates model experimentation from production qualification:

1. a candidate produces capability, privacy, and functional-workflow evidence;
2. qualifying evidence creates a validated runtime profile;
3. validated profiles are installed into Ally-owned configuration state; and
4. one installed profile may be selected as active.

Before this decision, daily private model commands still accepted raw endpoint
and model arguments as their normal interface. That made profile selection
advisory: a caller could bypass the validated-profile lifecycle simply by
supplying another local model string.

## Decision

Daily private inference resolves the selected validated runtime profile by
default.

The reusable `resolve_inference_target()` boundary returns one typed inference
target with explicit provenance:

- `validated_profile` for the currently selected, hash-bound validated
  runtime profile; or
- `development_override` only when both an explicit development endpoint and
  development model are supplied together.

Validated targets include the profile ID and runtime identity. Development
targets never claim validated profile identity.

Both target types remain loopback-only. A partial development override is
rejected, and there is no fallback from missing, malformed, removed, stale, or
tampered active profile state to localhost defaults or arbitrary model strings.

Private chat, model plan proposals, and model memory proposals all use this
resolver. Target resolution occurs before chat opens or creates conversation
state.

Validation and public/synthetic benchmarking commands retain their explicit
candidate endpoint/model inputs because their purpose is to produce evidence
before a candidate becomes eligible for selection.

## Consequences

Normal daily use no longer requires endpoint/model arguments after a validated
profile is installed and selected.

Candidate development remains possible through clearly named
`--development-endpoint` and `--development-model` options. Both must be
present and the endpoint must be loopback.

Future desktop/application composition should use the same inference-target
resolver rather than independently interpreting runtime profile state.
