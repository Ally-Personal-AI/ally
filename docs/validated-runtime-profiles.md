# Validated Runtime Profiles

A validated runtime profile is Ally's durable bridge between candidate evidence
and future production runtime selection.

## Create

After a candidate has all three qualifying artifacts:

```bash
ally profiles create \
  validation/<candidate>.json \
  validation/<candidate>-privacy.json \
  validation/<candidate>-workflows.json \
  --output validation/<candidate>-profile.json
```

Creation fails unless the exact evidence set is production-eligible.

## Inspect

```bash
ally profiles show validation/<candidate>-profile.json
```

Use `--json` for machine-readable output.

## Verify

```bash
ally profiles verify \
  validation/<candidate>-profile.json \
  validation/<candidate>.json \
  validation/<candidate>-privacy.json \
  validation/<candidate>-workflows.json
```

Verification rechecks the exact source hashes, candidate qualification, Ally
version, loopback endpoint, model/runtime identity, hardware, evaluation-suite
fingerprints, and performance observations.

## Identity

Profile identity is deterministic from the exact evidence digests **and** all
operational metadata copied from capability evidence: Ally version, endpoint,
model/runtime identity, hardware, evaluation fingerprints, and performance
observations. The creation timestamp is intentionally excluded.

This makes a metadata-only edit invalidate the profile before selection while
still yielding the same profile ID when the exact qualified evidence is rebuilt.

## Privacy

Profiles retain only evidence leaf filenames and hashes, never absolute evidence
paths. They contain no prompts, model responses, memories, personal documents,
credentials, or secrets.

## Selection boundary

The profile does not start or manage a model server. It certifies that one exact
runtime/model configuration is eligible for future selection.

Future desktop/runtime composition should select a validated profile and then
verify/launch the corresponding runtime. It should not reintroduce arbitrary
production endpoint/model strings as an alternate path around qualification.

After verification, install the profile into Ally's
[Runtime Profile Catalog](runtime-profile-catalog.md) and select it explicitly
for daily-use composition.
