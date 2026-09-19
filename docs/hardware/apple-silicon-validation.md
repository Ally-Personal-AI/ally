# Apple Silicon First-Machine Validation

This runbook is the handoff from hardware-independent Ally development to
empirical local-AI validation.

The goal is not merely to prove that a model answers prompts. It is to create
repeatable evidence about which local runtime/model combination should become
the first recommended Ally configuration.

GitHub CI includes a macOS portability smoke gate. That gate is useful for
catching operating-system differences in paths, SQLite, subprocesses, and other
deterministic behavior, but it is **not** first-machine validation. Hosted CI
does not establish target Apple Silicon model performance, unified-memory
headroom, context capacity, latency, or sustained thermal behavior.

## Safety and data rules

Use only the frozen synthetic evaluation cases in the repository during initial
validation. Do not import personal files, memory, email, credentials, or other
private data until the machine/runtime path is understood.

Keep the inference endpoint bound to loopback during validation.

## 1. Prepare the machine

Install Git and `uv`, clone the repository, and install the development
environment:

```bash
git clone https://github.com/Ally-Personal-AI/ally.git
cd ally
uv sync --extra dev
```

Verify the repository-independent environment:

```bash
uv run ally doctor
uv run ally validate hardware --json
uv run ruff check .
uv run pyright
uv run pytest
uv run ally eval run evals/cases/core.jsonl
```

All deterministic checks should pass before testing a model.

## 2. Start one local OpenAI-compatible inference server

The first comparison should test runtimes one at a time. Suitable candidates
include llama.cpp-compatible servers and Apple-optimized runtimes that expose
an OpenAI-compatible local endpoint.

Bind the server to `127.0.0.1`. Record:

- runtime and version
- model identifier
- model source
- quantization / precision
- configured context length
- runtime flags
- approximate model file size

Do not change multiple variables between comparison runs unless the run is
explicitly exploratory.

## 3. Run the reproducible Ally validation

With the server available at the default endpoint:

```bash
uv run ally validate local-model \
  --model <model-id> \
  --output validation/<runtime>-<model>.json
```

For another loopback endpoint:

```bash
uv run ally validate local-model \
  --endpoint http://127.0.0.1:11434/v1 \
  --model <model-id> \
  --output validation/<runtime>-<model>.json
```

The generated JSON contains:

- Ally version
- timestamp
- endpoint and model identifier
- machine/OS/Python profile
- deterministic core evaluation results
- provider smoke evaluation results
- evaluation duration

The report contains no personal data when the frozen cases are used.

## 4. Manual performance observations

The initial provider abstraction does not yet standardize token-usage telemetry
across runtimes, so record these runtime-native measurements alongside the JSON
artifact:

- model load time
- time to first token
- prompt-processing tokens/second
- generation tokens/second
- peak memory / memory-pressure state
- sustained temperature/fan behavior for a multi-turn session
- maximum tested context before unacceptable slowdown or memory pressure

Prefer runtime-native metrics over estimates.

## 5. Functional Ally checks

After provider smoke evaluation passes, use synthetic data to exercise:

1. persistent multi-turn chat and resume after process restart;
2. explicit memory creation, retrieval, supersession, and retraction;
3. synthetic document ingestion and grounded answers;
4. private-context safeguards;
5. `system.info` through the permissioned tool runtime;
6. a persisted read-only task using `system.info`;
7. task restart/resume behavior;
8. synthetic model plan proposal quality;
9. synthetic memory proposal quality and explicit review, without accepting
   personal data.

Do not enable automatic memory writes or consequential tools during the
first-machine session.

## 6. Compare runtimes/models

A candidate should not become the default merely because it has the highest raw
tokens/second. Compare:

- instruction reliability
- provider smoke pass rate
- usable context
- latency
- memory headroom
- runtime stability
- model quality on Ally's planning and memory-formation evaluations
- ease of reproducible installation
- compatibility with the model-provider boundary

Keep the raw JSON reports so future hardware and model changes can be compared
against the same baseline.

## Exit criteria

The first-machine phase is complete when at least one local runtime/model pair:

- passes deterministic Ally checks;
- passes provider smoke checks consistently;
- runs entirely on the local machine;
- has acceptable interactive latency;
- leaves enough memory headroom for Ally's database, retrieval, and future voice
  components;
- survives repeated conversation/task workflows without instability.

Only then should Ally add hardware-specific optimizations such as a direct MLX
adapter or choose a default local model.
