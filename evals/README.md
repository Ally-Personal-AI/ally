# Ally Evaluations

Ally treats evaluations as a first-class product subsystem.

## Core behavioral suite

The frozen deterministic suite runs in CI:

```bash
uv run ally eval run evals/cases/core.jsonl
```

Use `--json` for machine-readable output.

Current core categories cover:

- private-context network policy
- retrieved-context trust boundaries
- deterministic knowledge chunking
- memory retrieval behavior

These cases require no model, GPU, network service, or personal data.

## Provider smoke suite

The provider suite is ready for real local-model validation but is not a CI gate:

```bash
uv run ally eval provider evals/cases/provider-smoke.jsonl \
  --model <model-id>
```

The default endpoint is `http://127.0.0.1:8080/v1`.

Provider smoke cases validate basic inference contract behavior such as exact-token instruction following and system-message handling. They are not intended to measure general intelligence.

## Adding evaluations

Cases are newline-delimited JSON with:

- a stable unique `id`
- an evaluator `category`
- JSON `input`
- JSON `expected`
- optional `tags`

Evaluator implementations live under `src/ally/evals/` and must be registered explicitly.

Evaluation fixtures must use synthetic data unless a contributor deliberately adds appropriately licensed public data. Personal user data must never enter the repository.

## Future suites

The harness is designed to grow into:

- memory precision and recall
- temporal memory correctness
- provenance quality
- document retrieval quality
- tool selection and permission enforcement
- task completion and verification
- privacy/data-boundary regressions
- local-model quality, latency, and resource benchmarks
- regression comparisons across model/runtime versions
