# Functional Workflow Qualification

Ally validates integrated functionality in a disposable synthetic workspace and
records the result as immutable evidence tied to one exact local-model
capability report.

## Run

After `ally validate local-model` has produced a capability artifact and the
same loopback server is still running:

```bash
uv run ally validate workflows \
  validation/<candidate>.json \
  --output validation/<candidate>-workflows.json
```

The command derives the endpoint and model identifier from the capability
artifact. This prevents the functional run from being accidentally recorded
against a different model or endpoint.

The temporary workspace contains synthetic conversation, memory, knowledge,
task, tool-audit, backup, and restore state. It is deleted before the command
returns.

## Evidence contents

The artifact contains:

- Ally version;
- SHA-256 of the exact source capability artifact;
- copied model/runtime/hardware identity;
- source capability success state;
- each functional check ID and pass/fail state;
- check duration and safe exception class when a check fails; and
- total duration.

It does **not** contain model responses, prompt bodies, temporary filesystem
paths, generated SQLite contents, personal data, or credentials.

Artifacts are schema-versioned and never overwritten.

## Inspect and verify

```bash
uv run ally validate workflows-show \
  validation/<candidate>-workflows.json

uv run ally validate workflows-verify \
  validation/<candidate>-workflows.json \
  validation/<candidate>.json
```

Verification recomputes the capability artifact SHA-256 and also requires the
Ally version, model, runtime profile, hardware profile, and source success state
to match.

## Qualification

Functional evidence is qualified for candidate use only when:

- the source capability artifact itself passed; and
- every disposable functional check passed.

A failed artifact is still useful diagnostic evidence. Do not delete or rewrite
it; fix the cause and create a new workflow artifact.

Production eligibility additionally requires a separately qualified
[Runtime Privacy Qualification](runtime-privacy-qualification.md) artifact.
See [Apple Silicon First-Machine Validation](hardware/apple-silicon-validation.md)
for the complete three-artifact selection workflow.
