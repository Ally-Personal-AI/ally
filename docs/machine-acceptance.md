# Dedicated-Machine Acceptance Evidence

Ally's remaining 0.1 release gates are empirical. They depend on the actual
dedicated Mac, its operating-system security state, the selected validated local
runtime profile, and the signed application identity.

Those observations must not become an informal checklist that cannot be
re-verified later. Ally therefore records a small, versioned, payload-free
machine acceptance artifact.

## Authority boundary

The artifact records observations. It does not perform or bypass the underlying
acceptance work.

A passing value is meaningful only after the corresponding procedure in
[Unified First-Machine Acceptance](hardware/first-machine-acceptance.md) has been
completed on the dedicated machine.

Hosted CI uses synthetic pass values only to test serialization, packaging, and
verification mechanics. CI is never evidence that a real machine gate passed.

## Binding

Every report is bound to:

- the exact Ally package version;
- a full 40-character Git source revision;
- the exact collected hardware/OS profile;
- the currently selected validated runtime profile ID; and
- the SHA-256 recorded by Ally's hash-bound active-profile selection.

Before evidence is created or verified, the active validated runtime profile
must itself report the same Ally version and exact hardware/OS profile as the
current machine.

Verification fails if any of those values no longer match the current
installation.

An operating-system update, Ally version change, different source revision,
different machine, runtime-profile reselection with different bytes, or profile
tampering therefore requires new acceptance evidence.

## Fixed empirical gates

The report contains exactly these statuses:

- `keychain` — login-Keychain persistence, prompts, lock/unlock, missing/deleted state;
- `recovery` — backup/validate/restore and default-path recovery drill;
- `background_service` — signed-app Login Item, legacy migration, login/restart behavior;
- `notifications` — signed-app authorization, visibility, duplicate suppression, restart behavior;
- `signed_release` — real Developer ID identity, hardened runtime, trusted timestamp, notarization, Gatekeeper;
- `update_preparation` — forward candidate verification plus schema-safe backup preparation;
- `app_replacement` — staged replacement preserves user-owned state outside `Ally.app`;
- `integrated_daily_use` — final synthetic integrated desktop/runtime/recovery acceptance.

Each status is one of:

- `pass`
- `fail`
- `not_run`

There is no free-form notes field. Personal prompts, filesystem paths,
credentials, packet payloads, notification text, and other private data do not
belong in this artifact.

A report is qualified for release acceptance only when every fixed gate is
`pass`.

## Create evidence

After the validated runtime profile is installed and selected, and after the
empirical gates have actually been exercised:

```bash
uv run ally machine-acceptance create \
  --source-revision <40-character-git-sha> \
  --keychain pass \
  --recovery pass \
  --background-service pass \
  --notifications pass \
  --signed-release pass \
  --update-preparation pass \
  --app-replacement pass \
  --integrated-daily-use pass \
  --output validation/machine-acceptance.json \
  --json
```

Failed or unfinished checks may be recorded as `fail` or `not_run`. The
artifact is still useful diagnostic evidence, but it is not release-qualified.

Reports are immutable. Ally refuses to overwrite an existing destination. After
fixing a failed gate, create a new artifact rather than rewriting history.

## Verify current binding

```bash
uv run ally machine-acceptance verify \
  validation/machine-acceptance.json \
  --source-revision <40-character-git-sha> \
  --json
```

Verification re-collects the current hardware profile and re-resolves Ally's
hash-bound active validated profile.

Exit behavior:

- `0` — binding matches and all gates pass;
- `1` — binding matches, but at least one gate is `fail` or `not_run`;
- `2` — artifact, source revision, Ally version, hardware, or active-profile
  binding is invalid/inconsistent.

`show` inspects an artifact without asserting current binding:

```bash
uv run ally machine-acceptance show validation/machine-acceptance.json --json
```

## Release use

This artifact is the machine-side complement to the candidate-specific
capability, privacy, workflow, and validated-profile evidence.

It does not replace those artifacts and does not choose a model. A future tagged
Ally 0.1 release gate should require both:

1. a currently verified selected runtime profile derived from qualified candidate
   evidence; and
2. a currently verified dedicated-machine acceptance artifact.

Automatic update download/replacement remains disabled until the signed
release/update/replacement gates have actually passed on the dedicated Mac.

## Final release-readiness aggregation

Machine acceptance is one half of the final evidence-side release decision. The
other half is the selected runtime profile's exact capability/privacy/workflow
qualification.

Immediately before a tagged pre-release, run
`ally release readiness` with those source artifacts and this machine
acceptance report. The release-readiness gate re-verifies both chains against
the live installation; it does not publish or mutate anything.

See [Ally 0.1 Release Readiness](release-readiness.md).
