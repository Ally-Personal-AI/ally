# Local-model Validation Evidence

Ally treats runtime and model selection as an evidence decision. A candidate is
not recommended merely because it starts successfully or produces the highest
raw token rate.

## Versioned report contract

`ally validate local-model` writes a schema-versioned JSON artifact containing:

- the Ally version and generation timestamp;
- the loopback endpoint and model identifier;
- runtime name and exact version;
- optional public model source, quantization, precision, context length, and
  explicit non-secret runtime parameters;
- content fingerprints for the core, provider, and behavioral evaluation files;
- a non-sensitive machine profile;
- complete core, provider, and behavioral evaluation results;
- total evaluation duration; and
- optional runtime-native performance and resource observations.

Reports reject unknown top-level fields, inconsistent evaluation counts,
timestamps without a timezone, unsupported schema versions, and malformed
runtime metadata. Existing artifacts are never overwritten.

The frozen core, provider, and behavioral suites ship inside the installed package,
so the defaults work outside a source checkout. Use `--core-cases`,
`--provider-cases`, or `--behavior-cases` only for explicit custom files.
Fingerprints describe the actual files used;
relocating the bundled fixtures does not change their content or fingerprints.

Runtime parameters use repeated `NAME=VALUE` arguments. Names that identify
common credential material are rejected. Do not record credentials, private
paths, personal data, private model repository URLs, or arbitrary command
lines. The discrete fields and explicit parameters are an evidence manifest,
not a process dump.

## Recording a candidate

Start one OpenAI-compatible server on loopback, obtain its exact version and
runtime-native measurements, then run. Local-model validation is intentionally
loopback-only and cannot target an external inference provider:

```bash
uv run ally validate local-model \
  --endpoint http://127.0.0.1:8080/v1 \
  --model <model-id> \
  --runtime <runtime-name> \
  --runtime-version <exact-version> \
  --model-source <public-model-id> \
  --quantization <quantization> \
  --precision <precision> \
  --model-size-bytes <bytes> \
  --context-length <tokens> \
  --runtime-parameter <name>=<value> \
  --model-load-ms <milliseconds> \
  --time-to-first-token-ms <milliseconds> \
  --prompt-tokens-per-second <rate> \
  --generation-tokens-per-second <rate> \
  --peak-memory-bytes <bytes> \
  --maximum-tested-context-tokens <tokens> \
  --memory-pressure <normal|warning|critical|unknown> \
  --thermal-state <nominal|fair|serious|critical|unknown> \
  --output validation/<runtime>-<model>.json
```

Performance flags are optional because runtimes expose different telemetry.
Use runtime-native measurements rather than estimates. Omit a field instead of
inventing a value.

## Comparing candidates

Compare two or more reports in human-readable form:

```bash
uv run ally validate compare \
  validation/<candidate-a>.json \
  validation/<candidate-b>.json
```

Use `--json` for another machine-readable artifact. Comparison warns when the
Ally version, hardware profile, or evaluation fingerprints differ, because
behavior, performance, or pass counts then are not directly comparable.

The comparison preserves input order and never computes a composite score,
ranks candidates, or selects a default. Behavioral pass counts remain separate
from throughput and resource observations. Raw throughput cannot safely outweigh
instruction reliability, unnecessary-refusal behavior, viewpoint symmetry,
calibration, usable context, memory headroom, stability, or Ally's planning and
memory-proposal behavior. The operator makes that decision from
the complete evidence described in the first-machine runbook.

A successful local-model report is capability evidence only. It does not prove
that the selected runtime itself has no prompt-bearing telemetry, cloud fallback,
or required external egress. Before a candidate becomes eligible for private
daily use, create the separate fail-closed runtime privacy artifact described in
[Runtime Privacy Qualification](runtime-privacy-qualification.md).

## Evidence boundaries

Generated reports remain local and are ignored by Git. Frozen evaluation cases
contain synthetic data. Private user prompts/documents must not be used with an
external model during validation or evaluation. If a local candidate was tested
with personal prompts, private documents, credentials, or private model URLs,
do not treat the report as repository-safe even if those inputs are not
expected to appear in normal output.
