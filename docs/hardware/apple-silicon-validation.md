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

Keep the inference endpoint bound to loopback during validation. A candidate
runtime is not production-qualified merely because Ally talks to it over
loopback: the runtime itself must also demonstrate that it can operate without
external network access and does not require prompt/telemetry egress.

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
uv run ally eval run
```

All deterministic checks should pass before testing a model.

## 2. Accept the login-Keychain adapter

Use a new synthetic value that is not a real credential. Do not put the value
in the shell command, history, an environment variable, or this repository.

```bash
uv run ally secrets set validation.synthetic
uv run ally secrets check validation.synthetic
uv run ally secrets list
```

End the process and open a new shell, then run `check` and `list` again. Both
must report the reference, while neither command may display the value. Create
and inspect a normal Ally backup; it must still contain exactly
`manifest.json` and `ally.sqlite3`.

On the dedicated machine only, an operator who can safely unlock the login
Keychain should also exercise locked-state behavior. Lock the login Keychain
using Keychain Access, run `check`, and confirm Ally either receives an OS
unlock prompt or exits with the generic unavailable/denied message. It must
not print the value or raw Keychain diagnostic. Unlock the Keychain and confirm
`check` succeeds again.

Finally, remove the synthetic item and verify the missing status:

```bash
uv run ally secrets delete validation.synthetic
uv run ally secrets check validation.synthetic
```

The final `check` should exit with status 1. Record the macOS version and any OS
prompts observed. If setting, cross-process persistence, locked-state handling,
or deletion differs from this sequence, the Keychain milestone remains open.

## 3. Start one local OpenAI-compatible inference server

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
explicitly exploratory. Translate only reproducibility-critical, non-secret
flags into `--runtime-parameter NAME=VALUE`; never copy an arbitrary command
line, credential, private path, or access-bearing model URL into a report.

Before a runtime becomes eligible for private daily use, repeat the synthetic
validation with external network connectivity unavailable or explicitly denied
to the runtime. Confirm that inference still works and inspect for unexpected
outbound connections/telemetry. A runtime that requires external inference,
cloud authorization during normal operation, or prompt-bearing telemetry is
not eligible for Ally private inference.

Record that second phase as a separate immutable artifact using
`ally validate runtime-privacy`. Every privacy check defaults to `not_run`;
the artifact qualifies only when the source local-model report passed, the
evidence uses the same Ally version, an isolation/observation method is recorded,
and every required check passes. See
[Runtime Privacy Qualification](../runtime-privacy-qualification.md).

## 4. Run the reproducible Ally validation

With the server available at the default endpoint:

```bash
uv run ally validate local-model \
  --model <model-id> \
  --runtime <runtime-name> \
  --runtime-version <exact-version> \
  --model-source <public-model-id> \
  --quantization <quantization> \
  --model-size-bytes <bytes> \
  --context-length <tokens> \
  --output validation/<runtime>-<model>.json
```

For another loopback endpoint:

```bash
uv run ally validate local-model \
  --endpoint http://127.0.0.1:11434/v1 \
  --model <model-id> \
  --runtime <runtime-name> \
  --runtime-version <exact-version> \
  --model-source <public-model-id> \
  --quantization <quantization> \
  --model-size-bytes <bytes> \
  --context-length <tokens> \
  --output validation/<runtime>-<model>.json
```

The generated JSON contains:

- Ally version
- timestamp
- endpoint, model identifier, and non-secret runtime profile
- content fingerprints for all three frozen evaluation files
- machine/OS/Python profile
- deterministic core evaluation results
- provider smoke evaluation results
- behavioral qualification results by evaluation category
- optional runtime-native performance observations
- evaluation duration

Reports are schema-versioned and never overwrite an existing artifact. The
report contains no personal data when the frozen cases and public identifiers
are used.

## 5. Manual performance observations

The initial provider abstraction does not standardize token-usage telemetry
across runtimes. Obtain these measurements from the runtime itself:

- model load time
- time to first token
- prompt-processing tokens/second
- generation tokens/second
- peak memory / memory-pressure state
- sustained temperature/fan behavior for a multi-turn session
- maximum tested context before unacceptable slowdown or memory pressure

Prefer runtime-native metrics over estimates.

Record available numeric observations directly in the final validation
artifact with the matching options:

```bash
--model-load-ms <milliseconds>
--time-to-first-token-ms <milliseconds>
--prompt-tokens-per-second <rate>
--generation-tokens-per-second <rate>
--peak-memory-bytes <bytes>
--maximum-tested-context-tokens <tokens>
--memory-pressure <normal|warning|critical|unknown>
--thermal-state <nominal|fair|serious|critical|unknown>
```

Omit an unavailable measurement instead of estimating it. Use a new output
filename when repeating a run so prior evidence remains intact.

## 6. Functional Ally checks

After provider smoke and behavioral qualification complete, use synthetic data to exercise:

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

## 7. Compare runtimes/models

A candidate should not become the default merely because it has the highest raw
tokens/second. Compare:

- instruction reliability
- provider smoke pass rate
- unnecessary-refusal behavior
- instruction-following behavior
- calibration and unsolicited-moralizing checks
- paired viewpoint-symmetry evidence
- usable context
- latency
- memory headroom
- runtime stability
- model quality on Ally's planning and memory-formation evaluations
- ease of reproducible installation
- compatibility with the model-provider boundary
- ability to operate with external network egress unavailable
- absence of prompt-bearing telemetry or required cloud inference

Keep the raw JSON capability reports and matching runtime-privacy artifacts so
future hardware, runtime, and model changes can be compared against the same
baseline.

Compare candidate artifacts after each candidate has completed the same frozen
suite on the same machine:

```bash
uv run ally validate compare \
  validation/<candidate-a>.json \
  validation/<candidate-b>.json
```

The command warns when the Ally version, hardware, or evaluation fingerprints
differ and never selects a default automatically. See
[Local-model Validation Evidence](../model-validation.md) for the complete
artifact contract.

## Exit criteria

The first-machine phase is complete when at least one local runtime/model pair:

- passes deterministic Ally checks;
- passes provider smoke checks consistently;
- completes the frozen behavioral qualification suite with results reviewed by dimension;
- runs entirely on the local machine;
- continues to operate with external network egress unavailable;
- has no observed or required prompt-bearing telemetry/cloud inference;
- has acceptable interactive latency;
- leaves enough memory headroom for Ally's database, retrieval, and future voice
  components;
- survives repeated conversation/task workflows without instability.

Only then should Ally add hardware-specific optimizations such as a direct MLX
adapter or choose a default local model. A candidate without a qualified runtime
privacy artifact remains development-only even when the local-model validation
report passes.
