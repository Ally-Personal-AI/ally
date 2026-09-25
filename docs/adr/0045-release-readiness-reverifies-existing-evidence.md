# ADR 0045: Release readiness re-verifies existing evidence

## Status

Accepted

## Context

Ally has independent evidence for local runtime capability/behavior, runtime
privacy, functional workflows, validated runtime selection, and dedicated-machine
acceptance.

The Ally 0.1 release checklist previously described how those pieces combine,
but there was no single executable check proving that the exact currently active
installation still matched all of them.

Creating a new release authority would be unsafe. The release layer should not
be able to override candidate qualification, machine acceptance, model
selection, privacy policy, or signing trust.

## Decision

Add a read-only release-readiness aggregator.

It must re-use the existing authorities:

- validated runtime profile verification for capability/privacy/workflow
  evidence;
- hash-bound active profile selection;
- live hardware collection; and
- dedicated-machine acceptance binding/qualification.

The output is path-free and contains only non-secret identifiers, SHA-256
digests, and boolean qualification state.

The command does not write an evidence artifact, tag Git, build/sign/notarize an
application, publish a release, or perform updates.

Exit success means only that the evidence-side tagged pre-release gate is
currently satisfied.

## Consequences

- the prose release checklist gains an executable fail-closed counterpart;
- stale or copied candidate/machine evidence cannot silently qualify a release;
- changing the active profile, hardware/OS profile, Ally version, source
  revision, or source artifacts invalidates readiness;
- release readiness remains auditable without storing personal data or local
  paths; and
- release publication remains an explicit operator/release-workflow action
  outside this gate.
