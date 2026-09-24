# Runtime Profile Catalog

Validated runtime profiles can be installed into Ally-owned non-secret
configuration state and explicitly selected for future daily-use composition.

## Install

Installation re-verifies the profile against all exact source evidence:

```bash
ally profiles install \
  validation/<candidate>-profile.json \
  validation/<candidate>.json \
  validation/<candidate>-privacy.json \
  validation/<candidate>-workflows.json
```

An unverified, mismatched, or symlink-substituted source is rejected.

## List installed profiles

```bash
ally profiles installed
ally profiles installed --json
```

The active profile is marked separately.

## Select

```bash
ally profiles select <profile-id>
```

Selection stores the profile ID and the SHA-256 of the exact installed profile
bytes. It does not contact or start the model runtime.

## Resolve active profile

```bash
ally profiles active
ally profiles active --json
```

Resolution fails closed if the selected file is missing, malformed, replaced,
or changed after selection.

## Deselect and remove

```bash
ally profiles deselect
ally profiles remove <profile-id>
```

The active profile cannot be removed. Deselect it or select another validated
profile first.

## Data boundary

The catalog lives under Ally's configuration directory, separate from personal
conversation/memory/knowledge data.

Catalog and selection state contain no prompts, memories, model outputs,
credentials, source-evidence paths, or secrets.

## Composition contract

`resolve_active_runtime_profile()` is the reusable boundary for future
production composition.

Daily-use interfaces should resolve a validated active profile. Explicit raw
endpoint/model values remain appropriate for candidate development and
validation, but should not become an alternate production selection path.
