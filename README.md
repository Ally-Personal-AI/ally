# Ally

**Ally is a local-first, user-owned personal AI platform.**

Ally is being built toward a private, persistent artificial intelligence that can learn a user's world, remember accurately over long periods, use interchangeable local models, work with tools, and eventually act within explicit user-defined boundaries.

> Models are replaceable. Memory persists. Tools are extensible. Policies are programmable. Data belongs to the user. The assistant evolves.

## Status

Ally is in very early development. It is not yet suitable for consequential automation or storing irreplaceable sensitive information.

The first target, **Ally 0.1**, is a completely local, model-independent personal AI with persistent conversations, inspectable long-term memory, personal document knowledge, optional internet research, and strong local-data boundaries.

## Architecture

The foundational rule is simple:

**The LLM is a component inside Ally. Ally is not an application wrapped around one LLM.**

Inference engines such as MLX, llama.cpp, Ollama, CUDA-backed runtimes, and future systems sit behind Ally-owned provider interfaces. Replacing a model must not replace Ally's memory, identity, or higher-level behavior.

See:

- [Vision](docs/vision.md)
- [Principles](docs/principles.md)
- [Architecture](docs/architecture.md)
- [Codebase map](docs/codebase-map.md)
- [Security model](docs/security-model.md)
- [Memory model](docs/memory-model.md)
- [Roadmap](docs/roadmap.md)
- [Architecture decisions](docs/adr/README.md)

## Development

Ally currently targets Python 3.12 and uses [uv](https://docs.astral.sh/uv/) for environment and dependency management.

```bash
git clone https://github.com/Ally-Personal-AI/ally.git
cd ally
uv sync --extra dev
uv run ally doctor
uv run pytest
```

Quality checks:

```bash
uv run ruff check .
uv run pyright
uv run pytest --cov=ally
uv run ally eval run
```

Behavioral evaluation cases and contributor guidance live in [evals/README.md](evals/README.md).
The [clean-install check](CONTRIBUTING.md#clean-install-verification) also tests
the packaged release on Linux and macOS without a model server or dedicated hardware.

## Local inference

Ally's first private inference adapter talks to an OpenAI-compatible HTTP endpoint. Private inference is restricted to loopback addresses with no remote override, so prompts, conversation history, memory, documents, instructions, and derived personal intelligence are not sent to an external model provider.

Once a compatible local server is running:

```bash
uv run ally chat --model <model-id>
```

The default endpoint is:

```text
http://127.0.0.1:8080/v1
```

A different local endpoint can be selected explicitly:

```bash
uv run ally chat \
  --endpoint http://127.0.0.1:11434/v1 \
  --model <model-id>
```

Remote endpoints are rejected for private inference with no escape hatch.
The inference adapter ignores environment proxy settings so ambient shell
configuration cannot redirect local prompts.

A separately named public-evaluation path may benchmark a remote model only with
Ally's bundled synthetic/public fixtures and explicit
`--allow-remote-public`; custom evaluation files are rejected for remote runs.
See [Private Intelligence Boundary](docs/private-intelligence-boundary.md).

## Persistent conversations

Chat sessions are stored locally in Ally's SQLite database under the operating system's application-data directory.

Start a new conversation:

```bash
uv run ally chat --model <model-id>
```

Resume one:

```bash
uv run ally chat --model <model-id> --conversation <conversation-uuid>
```

Inspect local history without starting a model server:

```bash
uv run ally conversations list
uv run ally conversations show <conversation-uuid>
```

SQLite is behind an Ally-owned storage interface and versioned migrations; higher-level code does not depend directly on SQLite.

## Long-term memory

Memory V1 is structured, temporal, provenance-aware, and directly inspectable. Automatic model writes are intentionally not enabled; models can only produce reviewable memory proposals.

Store an explicit memory:

```bash
uv run ally memory remember "Synthetic fact" --kind semantic
```

Inspect and search:

```bash
uv run ally memory list
uv run ally memory search "synthetic"
uv run ally memory show <memory-uuid>
```

Correct or retract:

```bash
uv run ally memory supersede <memory-uuid> "Corrected fact"
uv run ally memory retract <memory-uuid>
```

Superseded and retracted records remain available for audit/history but are excluded from active-memory queries.

Ask a local model for reviewable candidates without writing them:

```bash
uv run ally memory propose "I prefer tea over coffee." \
  --model <model-id> \
  --source-type user \
  --output proposal.json
```

Inspect the JSON, then explicitly accept only selected indices:

```bash
uv run ally memory accept proposal.json --index 0
```

The model cannot choose source provenance or privacy, and proposal generation never touches the durable memory store.

## Personal knowledge

Knowledge V1 supports deterministic ingestion of UTF-8 plain-text files with immutable revision history.

Ingest a file:

```bash
uv run ally knowledge ingest ./notes.txt
```

Inspect and search:

```bash
uv run ally knowledge list
uv run ally knowledge show <source-uuid>
uv run ally knowledge search "greenhouse irrigation"
```

Re-ingesting unchanged content reuses the existing revision. Re-ingesting changed content creates a new revision while preserving prior chunks for audit and historical provenance.

Current knowledge and active memories can both ground local chat through the same provider-neutral context boundary.

Private chat always uses the loopback provider. Conversation history, memory,
knowledge grounding, and user instructions are not eligible for external model
inference.

## Permissioned tools

Tools are explicit capabilities with a declared risk class. Every invocation goes through Ally's deterministic permission policy and is written to the local audit log.

Inspect the default registry:

```bash
uv run ally tools list
```

Invoke the built-in read-only diagnostics tool:

```bash
uv run ally tools run system.info
```

Inspect recent attempts:

```bash
uv run ally tools audit
```

The initial policy allows read-only tools, requires explicit approval for reversible and externally consequential tools, and denies high-consequence tools. Models and future agents do not bypass this boundary.

## Persistent tasks

Task execution is a persisted state machine rather than an ephemeral agent loop. A task plan is JSON with an ordered set of tool steps:

```json
{
  "goal": "Inspect the local Ally runtime",
  "steps": [
    {
      "tool_name": "system.info",
      "arguments": {}
    }
  ]
}
```

Create and run it:

```bash
uv run ally tasks create ./task.json
uv run ally tasks run <task-uuid>
```

Inspect persisted state:

```bash
uv run ally tasks list
uv run ally tasks show <task-uuid>
```

If a step requires approval, execution pauses with `waiting_approval`. Resume only after explicitly naming the approved step:

```bash
uv run ally tasks run <task-uuid> --approve-step <step-uuid>
```

Failed steps remain failed until deliberately reset with `ally tasks retry`. Tool execution, permission policy, audit, and verification remain separate layers.

## Skills

Skills are declarative packages that compose capabilities without modifying Ally Core. Ally reads and validates `skill.toml` before any executable skill entrypoint is imported.

Inspect a package:

```bash
uv run ally skills inspect ./path/to/skill
```

Validate its required capabilities against an explicit runtime tool set:

```bash
uv run ally skills validate ./path/to/skill \
  --available-tool system.info
```

A skill may declare required tools, optional tools, and typed configuration fields, but the manifest cannot grant permission to execute anything.

Install a validated local package into Ally-owned storage:

```bash
uv run ally skills install ./path/to/skill
uv run ally skills installed
```

Newly installed skills are disabled by default. Enable, disable, or remove one explicit version:

```bash
uv run ally skills enable example.skill 1.0.0
uv run ally skills disable example.skill 1.0.0
uv run ally skills uninstall example.skill 1.0.0
```

Installation never imports the declared entrypoint, rejects symlinks and undeclared manifest fields, validates required tools against the real runtime registry, and copies the source into Ally-owned application data.

Executable Python skills must opt in separately with `execution = "python_subprocess_v1"`. Ally Core never imports their code. After explicit enablement, run one with bounded JSON input:

```bash
uv run ally skills run example.skill 1.0.0 \
  --input '{"value":"hello"}'
uv run ally skills audit
```

The initial execution mode launches a separate `python -I -S` process with a minimal environment, bounded stdin/stdout/stderr, a timeout, no Ally tools/config/secrets/private-state objects, and payload-free audit history. It is **process isolation, not a hardened OS sandbox**; the child still has the operating-system permissions of the user running Ally.

See [Isolated Skill Execution](docs/skill-execution.md) for the exact security boundary and contributor rules.

## Model plan proposals

A model may propose a typed `TaskPlan`, but proposal is deliberately separate from persistence and execution.

```bash
uv run ally plan propose \
  --model <model-id> \
  --goal "Inspect the local runtime"
```

The planner receives only the explicitly registered tool specifications, must return strict JSON, must preserve the requested goal exactly, and is rejected if it invents an undeclared tool. The proposal is printed for inspection; it is not automatically saved or executed.

Provider smoke validation includes a planning case so local models can be compared on their ability to produce bounded Ally plans.

## First-machine validation

The repository includes a reproducible handoff for dedicated local-AI hardware.

Inspect the local machine profile:

```bash
uv run ally validate hardware --json
```

With a loopback OpenAI-compatible model server running:

```bash
uv run ally validate local-model \
  --model <model-id> \
  --runtime <runtime-name> \
  --runtime-version <exact-version> \
  --quantization <quantization> \
  --context-length <tokens> \
  --output validation/<runtime>-<model>.json
```

This runs the same deterministic core evaluations used by CI plus provider smoke
evaluations and writes a versioned machine-readable report. The report includes
evaluation-file fingerprints and may record explicit non-secret runtime settings
and runtime-native performance observations. Existing evidence is never
overwritten.

Compare candidate reports without assigning an automatic score or default:

```bash
uv run ally validate compare \
  validation/<candidate-a>.json \
  validation/<candidate-b>.json
```

Generated validation artifacts are ignored by Git by default. See
[Local-model Validation Evidence](docs/model-validation.md) for the complete
report contract and command options.

A passing model-validation report is not enough to make a runtime eligible for
private daily use. The dedicated-machine session must also create a separate,
fail-closed runtime privacy artifact proving the candidate continues to work
under recorded no-egress conditions with no observed cloud fallback,
prompt-bearing telemetry, or unexpected outbound connections:

```bash
uv run ally validate runtime-privacy \
  validation/<candidate>.json \
  --isolation-mode host_offline \
  --network-observation system_tools \
  --output validation/<candidate>-privacy.json
```

All privacy checks default to `not_run`, so the example above remains
unqualified until each check is explicitly recorded as passed. See
[Runtime Privacy Qualification](docs/runtime-privacy-qualification.md).

On the dedicated machine, begin with the non-mutating readiness preflight:

```bash
uv run ally validate readiness
```

It checks the target platform, privacy configuration, packaged evaluation suites,
state/path boundaries, and native-attention API readiness without contacting a
model or mutating Ally state.

Once a candidate local model is running, exercise Ally's functional boundaries
without touching future personal state:

```bash
uv run ally validate workflows --model <model-id>
```

That workflow uses a disposable SQLite workspace and retains only payload-free
check results.

See [Apple Silicon First-Machine Validation](docs/hardware/apple-silicon-validation.md) for the full procedure and exit criteria.

## Proactive events

Ally now has a deterministic event and attention substrate. Events are persisted before any handler runs, and explicit importance maps to conservative attention classes:

```text
noise     -> ignore
routine   -> remember
important -> mention_later
urgent    -> notify
critical  -> interrupt
```

The default policy never produces `act`.

Emit a synthetic event:

```bash
uv run ally events emit calendar.changed \
  --source synthetic \
  --importance important \
  --payload '{"calendar":"example"}'
```

Inspect and mark events handled:

```bash
uv run ally events list --pending
uv run ally events show <event-uuid>
uv run ally events handle <event-uuid>
```

There is not yet a background event daemon or model-based attention classifier. Those future layers must build on this persisted boundary.

## Persisted schedules

Ally can persist one-shot and fixed-interval schedules as deterministic sources of proactive events.

Create a one-shot schedule:

```bash
uv run ally schedules create \
  --name "Synthetic reminder" \
  --event-type reminder.synthetic \
  --at 2026-10-01T09:00:00+00:00 \
  --importance important \
  --payload '{"message":"synthetic"}'
```

Add `--every-seconds <n>` for a fixed interval. Schedules may be inspected,
enabled, or disabled explicitly:

```bash
uv run ally schedules list
uv run ally schedules show <schedule-uuid>
uv run ally schedules disable <schedule-uuid>
uv run ally schedules enable <schedule-uuid>
```

Evaluate due schedules explicitly:

```bash
uv run ally schedules tick --at 2026-10-01T09:00:00+00:00
```

Missed interval occurrences are coalesced into one event rather than replayed as
a storm. Scheduled events use persisted dedupe keys so retrying after a partial
failure does not duplicate an already-created event.

There is intentionally no scheduler daemon yet. A future OS service will call
this same persisted boundary.

## Attention delivery

User-facing delivery is separate from event acknowledgement. Ally currently
delivers only `mention_later`, `notify`, and `interrupt` events through
explicit sinks; `act` is not a notification path.

Inspect pending attention:

```bash
uv run ally attention pending
```

Deliver through the development console sink:

```bash
uv run ally attention deliver --sink console
```

On macOS, the native Notification Center sink is also available:

```bash
uv run ally attention deliver --sink macos
uv run ally attention health --sink macos
```

The native sink renders only an explicit bounded `summary`/`message` field
(or the event type) rather than serializing the full event payload. See
[macOS Native Attention](docs/macos-notifications.md).

Inspect durable delivery history:

```bash
uv run ally attention history
uv run ally attention history --status failed
```

A successful delivery is terminal for that event/sink pair but does not mark
the event handled. Failed attempts remain retryable. Sinks receive a stable
delivery key so future external interfaces can implement idempotent retries.

The console sink remains useful for deterministic development. The current
macOS native adapter is intentionally isolated because it uses the legacy
CLI-compatible Notification Center API; a future bundled desktop shell should
replace that backend with modern authorization-aware User Notifications.
Mobile and voice delivery remain future sinks behind the same durable boundary.

## Proactive service cycle

The persisted proactivity components can be composed into one bounded runtime
operation without starting a daemon:

```bash
uv run ally service cycle
```

The service uses `--sink auto` by default: native Notification Center on
macOS and console elsewhere. Tests or operators may choose an explicit sink.

Use an explicit time for deterministic testing:

```bash
uv run ally service cycle \
  --at 2026-10-01T09:00:00+00:00 \
  --schedule-limit 100 \
  --delivery-limit 50 \
  --lease-seconds 300
```

A cycle evaluates due schedules first and then delivers pending attention, so an
event produced by a due schedule can be surfaced in the same cycle. The command
returns nonzero when a sink delivery attempt fails and can emit a structured
report with `--json`.

Before doing any work, the cycle acquires a short-lived `proactive-cycle`
lease in Ally's disposable runtime database. A second overlapping invocation
fails before schedules or delivery side effects begin. Inspect runtime leases:

```bash
uv run ally service leases
```

Lease coordination lives under `<data-dir>/runtime/service.sqlite3`, separate
from personal state in `ally.sqlite3`, and is intentionally excluded from
backup V1.

This is still a one-shot operation. It does not sleep, loop, or daemonize.
Ally's optional macOS launch agent invokes this same bounded boundary; other OS
service wrappers are not implemented.

## Opt-in macOS managed service

Inspect the exact launch-agent definition without installing anything (this is
safe on every platform):

```bash
uv run ally service managed inspect
```

On macOS, installation is an explicit user action:

```bash
uv run ally service managed install
uv run ally service managed status --json
```

The agent runs `ally service cycle --json` once per minute and at login. The
service-cycle `auto` sink therefore selects native Notification Center on
macOS. It uses the current absolute Python interpreter path, writes only
stdout/stderr logs under Ally's data directory, and never invokes a shell. Ally
will not replace a different or modified plist at the same path.

```bash
uv run ally service managed stop
uv run ally service managed start
uv run ally service managed uninstall
```

Merely installing Ally never installs or enables this agent. Dedicated-machine
login, restart, failure-recovery, and log-retention acceptance remain part of
the hardware handoff. See [Managed macOS Service](docs/macos-managed-service.md).

## Service lifecycle and health

The ephemeral lease answers **who may run now**. Separately, each lease-protected
proactive cycle writes payload-free lifecycle history to the user-owned
`ally.sqlite3` database.

Inspect portable history:

```bash
uv run ally service history
uv run ally service history --json
```

Inspect health without mutating or migrating either database:

```bash
uv run ally service health
uv run ally service health --json
```

Lifecycle records contain only run IDs, statuses, timestamps, schedule/delivery
counts, and safe exception classes. They never copy event payloads, prompts,
documents, notification bodies, credentials, arbitrary exception messages, or
model output.

If a process exits after writing a portable `running` record, the next process
first acquires the ephemeral lease and only then repairs that abandoned history
as `interrupted`. The portable single-running constraint is a consistency
guard, not an overlap lock.

Health is a structured read-only readiness report. It validates an existing
non-secret config, checks both SQLite databases without writing or migrating
them, verifies that core migration history is an exact supported prefix, counts
active/expired runtime leases, and cross-checks a portable `running` lifecycle
record against the `proactive-cycle` lease.

Each check is `ok`, `warning`, or `error`. Overall status is `healthy`,
`degraded`, or `unhealthy`, with exit codes `0`, `1`, and `2`
respectively. Missing uninitialized state is a warning; corrupt or unsupported
state is an error.

See [Service Health and Readiness](docs/service-health.md) for the stable check
IDs and contributor rules.

## External event sources

External integrations observe changes and return bounded, validated observations
through Ally's `EventSource` protocol. Ally owns event persistence, dedupe,
attention policy, and source checkpoints.

A local JSONL reference adapter is included for deterministic development:

```json
{"external_id":"obs-1","event_type":"synthetic.changed","importance":"important","payload":{"value":1}}
```

Poll it:

```bash
uv run ally sources poll-jsonl \
  --source-id synthetic.source \
  ./events.jsonl
```

Inspect persisted source state:

```bash
uv run ally sources checkpoints
uv run ally sources checkpoint synthetic.source
```

Each observation has a stable external ID. Ally derives an event dedupe key from
the source ID and external ID, then advances the source's opaque cursor only
after returned observations have been published. If Ally stops between those
steps, replay reuses the already-persisted events rather than duplicating them.

The JSONL source remains a development/reference adapter. A real local
filesystem adapter can poll metadata below one explicitly selected root:

```bash
uv run ally sources poll-filesystem \
  --source-id files.documents \
  ./Documents
```

Its first poll establishes a quiet baseline. Later bounded polls emit created,
modified, moved, and deleted events without reading file contents or following
symlinks. Hidden entries are excluded by default. See
[Local filesystem event source](docs/filesystem-source.md) for its privacy,
pagination, rename, and failure semantics.

Future calendar, email, weather, deployment, and device integrations should
implement the same source boundary.

## Data portability

Ally V1 backups are user-owned, versioned ZIP archives containing exactly:

```text
manifest.json
ally.sqlite3
```

Create and validate a backup:

```bash
uv run ally data backup backups/ally-2026-09-19.ally-backup
uv run ally data validate backups/ally-2026-09-19.ally-backup
```

Restore into a clean database path:

```bash
uv run ally data restore backups/ally-2026-09-19.ally-backup \
  --destination ./restored-ally.sqlite3
```

Archives record the Ally version, database schema history, byte size, and SHA-256 digest. Validation also runs SQLite integrity checks. Backup and restore refuse to overwrite existing files.

Upgrades are atomic and reject incompatible migration history. Restore validates
foreign keys and upgrades a staged copy before creating a new destination, with
protection against competing writers and symbolic links. See the
[database recovery runbook](docs/database-recovery.md) before upgrading or restoring.

Backup V1 includes user-owned SQLite state, including portable service lifecycle
history. It deliberately excludes the disposable runtime lease database, model
weights, caches, configuration, logs, and secrets.

## Configuration and secrets

Ally configuration is versioned, strict, and deliberately non-secret.

```bash
uv run ally config path
uv run ally config show
uv run ally config init
uv run ally config validate
```

The current config schema contains only loopback private-inference defaults and a hard local-only privacy invariant. Unknown fields are rejected.

Credentials are represented by opaque `SecretRef` names and resolved through the `SecretStore` interface. On macOS, Ally has a Keychain adapter and a reference-only CLI:

```bash
uv run ally secrets set service.api-token
uv run ally secrets list
uv run ally secrets check service.api-token
uv run ally secrets delete service.api-token
```

`set` reads from a non-echoing interactive prompt. No command prints or exports a secret value, and non-macOS or unavailable Keychain state fails closed. CI includes a real Security-framework round trip with an ephemeral synthetic item; actual login-Keychain persistence remains an explicit dedicated-machine acceptance check.

See [Configuration and Secrets](docs/configuration-secrets.md).

## Personal data boundary

Personal runtime data, memory databases, secrets, downloaded model weights, generated indexes, and private logs are deliberately kept outside the repository.

Development fixtures must use synthetic or appropriately licensed public data.

## Contributing

Ally is being designed as an open ecosystem. The project is still foundational, so architectural consistency matters more than adding features quickly. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

## License

Apache License 2.0. See [LICENSE](LICENSE).
