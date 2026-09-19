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
uv run ally eval run evals/cases/core.jsonl
```

Behavioral evaluation cases and contributor guidance live in [evals/README.md](evals/README.md).

## Local inference

Ally's first inference adapter talks to an OpenAI-compatible HTTP endpoint. The endpoint is restricted to loopback addresses by default so local prompts do not silently leave the machine.

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

Remote endpoints are intentionally rejected unless `--allow-remote` is supplied.

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

Memory V1 is structured, temporal, provenance-aware, and directly inspectable. Automatic LLM memory extraction is intentionally not enabled yet.

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

For remote inference, `--allow-remote` permits the prompt/conversation to leave the machine, but private memory/document grounding remains disabled unless the separate `--allow-private-context-remote` flag is also supplied.

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
  --output validation/<runtime>-<model>.json
```

This runs the same deterministic core evaluations used by CI plus provider smoke evaluations and writes a machine-readable report. Generated validation artifacts are ignored by Git by default.

See [Apple Silicon First-Machine Validation](docs/hardware/apple-silicon-validation.md) for the full procedure and exit criteria.

## Personal data boundary

Personal runtime data, memory databases, secrets, downloaded model weights, generated indexes, and private logs are deliberately kept outside the repository.

Development fixtures must use synthetic or appropriately licensed public data.

## Contributing

Ally is being designed as an open ecosystem. The project is still foundational, so architectural consistency matters more than adding features quickly. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

## License

Apache License 2.0. See [LICENSE](LICENSE).
