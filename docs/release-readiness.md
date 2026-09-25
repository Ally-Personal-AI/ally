# Ally 0.1 Release Readiness

Ally's release decision is a verification step, not another authority layer.

The runtime candidate and the dedicated machine already have independent
evidence contracts. The release-readiness gate re-verifies those exact inputs
against the currently active installation and reports whether they jointly
satisfy the minimum Ally 0.1 tagged pre-release boundary.

It does not build, sign, notarize, tag, upload, publish, replace code, select a
model, or mutate Ally state.

## Required inputs

The gate requires:

1. the exact capability evidence used by the active validated runtime profile;
2. the exact runtime-privacy evidence used by that profile;
3. the exact functional-workflow evidence used by that profile;
4. the dedicated-machine acceptance artifact from the current installation; and
5. the full 40-character Git source revision being considered for release.

The active runtime profile must already be installed and selected.

## Verification chain

`ally release readiness` fails closed unless:

- the active profile file still matches the hash-bound active selection;
- the profile's Ally version matches the current Ally version;
- the profile's hardware/OS evidence matches the current machine;
- the capability/privacy/workflow artifacts still reproduce the active profile's
  exact path-free SHA-256 evidence references;
- the three candidate artifacts remain jointly production-eligible;
- the machine-acceptance artifact matches the current Ally version;
- the machine-acceptance artifact matches the supplied Git source revision;
- the machine-acceptance artifact matches the current hardware/OS profile;
- the machine-acceptance artifact matches the active profile ID and selection
  SHA-256; and
- every fixed machine-acceptance gate is `pass`.

No composite model-quality score or automatic model choice is introduced.

## Command

```bash
SOURCE_REVISION="$(git rev-parse HEAD)"

uv run ally release readiness \
  validation/candidate-a/capability.json \
  validation/candidate-a/privacy.json \
  validation/candidate-a/workflows.json \
  validation/machine-acceptance.json \
  --source-revision "$SOURCE_REVISION" \
  --json
```

The successful JSON result is path-free. It surfaces only:

- Ally version;
- source revision;
- active profile ID;
- active profile selection SHA-256;
- capability/privacy/workflow SHA-256 values;
- machine-acceptance artifact SHA-256;
- candidate production eligibility;
- machine acceptance qualification; and
- final tagged-pre-release readiness.

## Exit behavior

- `0` — the exact active candidate and machine evidence both verify and qualify;
- `1` — all bindings verify, but machine acceptance is not yet fully passed;
- `2` — evidence is missing, malformed, stale, mismatched, or the active
  installation cannot be trusted.

Exit `0` means the evidence-side release gate is satisfied. It does not perform
the release.

The actual release workflow must still use the documented signed/notarized
bundle procedure and should run this command immediately before a tagged
pre-release is created.

## CI boundary

Installed-wheel CI uses synthetic evidence to prove the command works from a
clean package on Linux and macOS.

That synthetic success is not evidence that the dedicated Mac or a real local
runtime passed acceptance. Only the real artifacts produced on the target
machine can satisfy the production release gate.
