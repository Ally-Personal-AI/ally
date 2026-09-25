# Final Release Readiness Evidence

Ally's release-readiness gate is evidence coordination, not release authority.

It ties the exact runtime-candidate qualification chain to the exact
dedicated-machine acceptance artifact. It does not create a Git tag, publish a
release, sign code, download updates, replace applications, select a model, or
change any machine state.

## Required source chain

A release-readiness report requires:

1. one immutable validation-session manifest;
2. passing capability evidence;
3. passing source-bound functional workflow evidence;
4. passing source-bound runtime privacy evidence;
5. a validated runtime profile that still verifies against those exact artifacts;
6. that exact profile selected in Ally's hash-bound installed-profile catalog;
7. a dedicated-machine acceptance artifact bound to the same current machine,
   source revision, and active profile.

The report records SHA-256 digests for the validation-session manifest,
capability evidence, privacy evidence, workflow evidence, validated profile, and
machine-acceptance artifact.

It contains no filesystem paths, prompt content, model responses, credentials,
notification text, packet captures, or free-form operator notes.

## Qualification

The candidate evidence stages must currently verify and pass before a final
readiness artifact can be created.

Machine acceptance may contain `fail` or `not_run` values; such a report is
useful as immutable diagnostic evidence but is not release-qualified.

The validation-session readiness stage is re-collected from the current machine.
Therefore a report is qualified for release only when:

- the candidate validation session is currently complete; and
- the dedicated-machine acceptance artifact has every empirical gate passed.

The source validated profile must also have the current Ally version and exact
current hardware/OS profile. Its serialized bytes must match the SHA-256 stored
in Ally's active-profile selection.

## Create

After the dedicated-machine runbook is complete:

```bash
SOURCE_REVISION="$(git rev-parse HEAD)"

uv run ally release-readiness create \
  validation/candidate-a/session.json \
  validation/machine-acceptance.json \
  --source-revision "$SOURCE_REVISION" \
  --output validation/release-readiness.json \
  --json
```

Creation refuses missing, inconsistent, source-mismatched, or non-active
candidate evidence. Existing destinations are never overwritten.

A successfully created artifact is not necessarily release-qualified. Inspect
`qualified_for_release`.

## Verify

Before tagging or distributing a release:

```bash
uv run ally release-readiness verify \
  validation/release-readiness.json \
  validation/candidate-a/session.json \
  validation/machine-acceptance.json \
  --source-revision "$SOURCE_REVISION" \
  --json
```

Verification re-derives the current validation-session state, re-verifies
machine acceptance, re-resolves the active profile, recomputes all source
digests, and requires the reconstructed report to match the immutable artifact
exactly.

Exit behavior:

- `0`: every source still matches and the report is release-qualified;
- `1`: every source still matches, but current readiness or machine acceptance
  is incomplete/failed;
- `2`: evidence is invalid, inconsistent, stale, source-mismatched, symlinked,
  or bound to a different Ally version/source/hardware/profile.

`show` inspects the artifact without checking live sources:

```bash
uv run ally release-readiness show validation/release-readiness.json --json
```

## Hosted CI boundary

Clean-install Linux and macOS CI exercise artifact creation and inspection using
synthetic evidence.

Hosted runners are not the dedicated Ally machine. CI must never be interpreted
as satisfying the real machine-readiness or machine-acceptance gates, even if a
synthetic report happens to contain passing machine statuses.

## Release boundary

A future tagged Ally 0.1 release workflow may consume a currently verified,
qualified release-readiness report as an input gate.

That future workflow must remain separate from this evidence layer. In
particular, this layer has no network transport, signing credential access,
GitHub release authority, update authority, or executable replacement authority.
