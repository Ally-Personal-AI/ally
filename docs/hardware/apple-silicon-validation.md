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

Create a dedicated validation session for each candidate so progress can be
resumed safely across process exits or reboots:

```bash
uv run ally validation-session init candidate-a \
  --directory validation/candidate-a
```

Use the artifact names planned by that session for all commands below. At any
point, inspect live derived progress with:

```bash
uv run ally validation-session refresh \
  validation/candidate-a/session.json
```

Before any mutable acceptance step, run the read-only first-machine preflight:

```bash
uv run ally validate readiness
uv run ally validate readiness --json
```

The readiness command does not contact a model, create/migrate databases,
initialize config, write Keychain, mutate launchd, or deliver a notification.
Warnings such as unconfirmed notification authorization do not block synthetic
model validation. Any `error` check must be resolved before continuing.

Then verify the repository-independent environment:

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
- exact model weight/shard artifact paths for local hashing
- stable runtime binary/package artifact paths when available

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
  --model-artifact <local-weight-or-shard> \
  --runtime-artifact <local-runtime-binary-or-package> \
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
- path-free SHA-256/size fingerprints for supplied model/runtime artifacts
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

## 6. Run isolated synthetic Ally workflows

Do not use Ally's default personal-state database for functional validation.
Run the isolated synthetic workflow from the exact capability artifact while
the same candidate server is still running:

```bash
uv run ally validate workflows \
  validation/<candidate>.json \
  --output validation/<candidate>-workflows.json
```

The endpoint and model are read from the capability artifact, so workflow
evidence cannot accidentally be attributed to another candidate. Use `--json`
for machine-readable status.

The command creates a temporary Ally SQLite database and synthetic knowledge
inside a disposable workspace, exercises the real runtime/store/policy
boundaries, and removes the workspace before returning. It does not initialize
the normal config, touch the default personal database, access Keychain, mutate
launchd, deliver notifications, or perform external egress.

The workflow checks:

1. persistent multi-turn conversation and resume through a reopened runtime;
2. explicit memory create/search/supersede/retract lifecycle;
3. synthetic knowledge ingestion/retrieval plus model-grounded answering;
4. `system.info` through the read-only permissioned tool path and audit;
5. a persisted read-only task using `system.info`;
6. a model TaskPlan proposal constrained to the declared tool;
7. a model memory proposal from synthetic source text without accepting it into
   durable memory;
8. backup, integrity validation, restore, and recovered synthetic state; and
9. that all generated validation state lives under the disposable workspace.

The immutable report stores the source capability SHA-256, copied
model/runtime/hardware identity, check IDs, pass/fail state, durations, and safe
exception class names. Model responses, synthetic prompts, temporary filesystem
paths, and generated database content are not copied into the report.

Verify the binding explicitly when desired:

```bash
uv run ally validate workflows-verify \
  validation/<candidate>-workflows.json \
  validation/<candidate>.json
```

A failed workflow remains useful diagnostic evidence but cannot qualify the
candidate for production use.

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

Keep the raw JSON capability reports plus their matching runtime-privacy and
functional-workflow artifacts so future hardware, runtime, and model changes can
be compared against the same baseline.

Capability-only comparison remains available, but production selection uses
three verified artifacts per candidate.

Inspect one exact evidence set:

```bash
uv run ally validate candidate \
  validation/<candidate-a>.json \
  validation/<candidate-a>-privacy.json \
  validation/<candidate-a>-workflows.json
```

Compare multiple verified candidates:

```bash
uv run ally validate compare-candidates \
  --candidate validation/<candidate-a>.json validation/<candidate-a>-privacy.json validation/<candidate-a>-workflows.json \
  --candidate validation/<candidate-b>.json validation/<candidate-b>-privacy.json validation/<candidate-b>-workflows.json
```

Both secondary artifacts are cryptographically verified against the exact same
capability report before comparison. The command shows capability, privacy, and
functional qualification separately. Production eligibility requires all three;
comparison never selects or ranks a default.

After choosing a candidate from the evidence, create the immutable runtime
profile that future Ally composition will consume:

```bash
uv run ally profiles create \
  validation/<candidate>.json \
  validation/<candidate>-privacy.json \
  validation/<candidate>-workflows.json \
  --output validation/<candidate>-profile.json

uv run ally profiles verify \
  validation/<candidate>-profile.json \
  validation/<candidate>.json \
  validation/<candidate>-privacy.json \
  validation/<candidate>-workflows.json
```

Do not configure daily-use runtime selection directly from raw endpoint/model
strings after a validated profile exists.

Finally, require the session itself to re-derive a complete state:

```bash
uv run ally validation-session verify \
  validation/candidate-a/session.json
```

This verification does not trust cached checkboxes; it re-validates current
readiness plus every evidence/profile artifact.

Capability-only `ally validate compare` remains useful during exploratory
testing. See [Local-model Validation Evidence](../model-validation.md) and
[Runtime Privacy Qualification](../runtime-privacy-qualification.md) for the
artifact contracts.

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
adapter or choose a default local model. A candidate without both qualified
runtime-privacy and functional-workflow artifacts remains development-only even
when the local-model validation report passes.
