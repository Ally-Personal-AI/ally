# Ally Evaluations

Ally treats evaluations as a first-class product subsystem.

## Core behavioral suite

The frozen deterministic suite runs in CI:

```bash
uv run ally eval run
```

Use `--json` for machine-readable output.

Frozen cases live in `src/ally/evals/cases/` and ship with the installed package.
Defaults are independent of the current working directory. Pass an explicit
JSONL path to run a custom suite: `ally eval run /path/to/custom.jsonl`.

Current core categories cover:

- private-context network policy
- retrieved-context trust boundaries
- deterministic knowledge chunking
- memory retrieval behavior

These cases require no model, GPU, network service, or personal data.

## Provider smoke suite

The provider suite is ready for real local-model validation:

```bash
uv run ally eval provider \
  --model <model-id>
```

The default endpoint is `http://127.0.0.1:8080/v1`.
An optional JSONL path overrides the bundled provider suite for local inference.
CI exercises its installed wiring with synthetic HTTP responses; real model
behavior remains a manual hardware-validation step.

An operator may explicitly benchmark a remote model with
`--allow-remote-public`, but only with Ally's bundled frozen synthetic/public
suite. Remote runs reject custom JSONL case files before contacting the
endpoint.

Provider smoke cases validate basic inference contract behavior such as exact-token instruction following and system-message handling. They are not intended to measure general intelligence.

## Behavioral qualification suite

The bundled behavioral suite is intended for candidate-model qualification
rather than deterministic CI because real model outputs vary:

```bash
uv run ally eval behavior --model <model-id>
```

The current suite records evidence in separate categories:

- unnecessary refusal on legitimate analytical requests;
- instruction following;
- epistemic calibration;
- unsolicited moralizing/evasive assistant framing; and
- paired viewpoint symmetry.

Paired cases send two opposing framings under the same instructions and compare
the responses using the same structural criteria, including minimum substance,
required requested sections, refusal behavior, and a bounded response-length
ratio. The evaluator does not decide which viewpoint is correct.

Behavioral fixtures use synthetic/public prompts only. The suite should grow
through balanced paired cases and additional objective checks rather than a
single opaque alignment score.

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
