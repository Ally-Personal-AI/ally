# Codebase Map

This guide is the quickest way for a new contributor to understand where code
belongs in Ally.

The most important rule is dependency direction:

> Interfaces and composition depend on Ally Core. Core does not depend on the
> CLI, command handlers, or concrete SQLite adapters.

## Package map

| Path | Responsibility |
| --- | --- |
| `src/ally/cli.py` | Argument parsing and top-level CLI dispatch only. |
| `src/ally/commands/` | CLI presentation adapters and output formatting. |
| `src/ally/application/` | UI-neutral typed daily-use services shared by CLI and local interfaces, including chat, memory, knowledge, tasks, attention views, and service observability. |
| `src/ally/desktop/` | Local desktop presentation adapters, including the bounded stdio bridge into `AllyApplication`. |
| `desktop/macos/` | Native SwiftUI presentation client and its Foundation-only bridge/protocol models. |
| `src/ally/composition/` | Reusable concrete dependency assembly for application/presentation surfaces. |
| `src/ally/runtime/` | Provider-neutral runtime workflows, including persistent and grounded conversation orchestration. |
| `src/ally/service/` | Bounded proactive service-cycle logic, lifecycle metadata, and runtime coordination contracts. |
| `src/ally/conversations/` | Conversation domain models and persistence contract. |
| `src/ally/memory/` | Long-term memory models, retrieval, proposal extraction, and persistence contract. |
| `src/ally/knowledge/` | Personal knowledge ingestion, chunking, retrieval, models, and persistence contract. |
| `src/ally/context/` | Provider-neutral retrieval/context composition and rendering. |
| `src/ally/models/` | Model-provider contracts, registry, errors, and provider adapters under `models/providers/`. |
| `src/ally/planning/` | Strict model-generated task-plan proposal boundary. |
| `src/ally/tools/` | Tool specifications, registry, execution, and audit contracts. |
| `src/ally/security/` | Deterministic network and tool-permission policy. |
| `src/ally/tasks/` | Persisted task state machine, execution, verification, and storage contract. |
| `src/ally/events/` | Persisted event domain and deterministic attention classification. |
| `src/ally/scheduler/` | One-shot/fixed-interval schedule domain and runtime. |
| `src/ally/sources/` | Restart-safe external event-source contracts, the reference JSONL adapter, and bounded metadata-only filesystem observation. |
| `src/ally/attention/` | Interface-neutral user-attention delivery contracts/runtime. |
| `src/ally/skills/` | Skill manifests, local lifecycle, isolated execution, and execution-audit contracts. |
| `src/ally/configuration/` | Strict non-secret configuration schema and file storage. |
| `src/ally/secrets/` | Secret references, secret-store contract, and macOS Keychain adapter. |
| `src/ally/portability/` | Versioned backup/validation/restore of user-owned SQLite state. |
| `src/ally/storage/` | Storage paths and concrete persistence adapters. |
| `src/ally/storage/sqlite/` | SQLite implementations of Ally-owned persistence contracts and migrations. |
| `src/ally/diagnostics/` | Read-only hardware, validation, and service-readiness diagnostics. |
| `src/ally/evals/` | Behavioral evaluation framework and frozen packaged suites under `cases/`. |
| `scripts/` | Distribution build checks and synthetic workflows for a clean installed package. |

## Dependency direction

A useful mental model is:

```text
CLI / future desktop / local clients
      |
      v
presentation adapters
      |
      v
application services
      |
      v
composition + runtime/service workflows
      |
      v
domain capabilities and Ally-owned protocols
(memory, knowledge, conversations, tools, tasks, events, skills, ...)
      |
      +--------------------+
      |                    |
      v                    v
storage contracts      model contracts
      |                    |
      v                    v
SQLite adapters        provider adapters
```

Cross-domain collaboration is allowed when it represents a real Ally concept.
For example, the proactive service cycle composes scheduler and attention
runtimes. What should not happen is a reusable domain package reaching upward
into CLI commands or downward into a concrete SQLite implementation.

## Enforced boundaries

`tests/test_architecture_boundaries.py` enforces a deliberately small set of
high-value rules:

1. packages below the interface layer do not import `ally.commands`;
2. reusable packages do not import `ally.cli`;
3. core/domain packages do not import `ally.storage.sqlite`.

Concrete storage is composed at explicit infrastructure/composition edges.
`ally.application` remains protocol-based; `ally.composition`, diagnostics,
portability, commands that have not yet migrated, and storage itself are the
reviewed concrete-adapter edges.

These tests are guardrails, not a complete dependency graph. Add a new rule only
when it protects a durable architectural property and can be explained simply.

## Where should new code go?

Use these questions in order:

1. **Is this argument parsing or user-facing formatting?** Put CLI concerns in
   `cli.py` or `commands/`; native macOS presentation belongs under
   `desktop/macos/` and local bridge adaptation under `src/ally/desktop/`.
2. **Is this a daily-use workflow shared across interfaces?** Put UI-neutral
   orchestration in `application/`.
3. **Is this concrete dependency assembly?** Put it in `composition/`.
4. **Is this a reusable domain concept or lower-level runtime?** Put it in the
   corresponding domain/runtime package behind an Ally-owned interface.
5. **Is this a vendor, database, operating-system, or network implementation?**
   Put it behind the relevant interface in an adapter/infrastructure package.
6. **Is this a hard-to-reverse architectural choice?** Add or update an ADR.
7. **Does this introduce private fixture data?** Stop. Tests and examples must
   remain synthetic or appropriately licensed public data.

## Adding a new subsystem

A new top-level package should have a narrow purpose that existing packages
cannot express cleanly. Prefer:

- domain models;
- small protocols/ports;
- deterministic runtime behavior;
- an adapter at the edge;
- focused unit/integration tests;
- a short contributor-facing document if the boundary is not obvious.

Do not create a new package merely to avoid choosing an existing owner for the
code.

## Reading order for new contributors

1. [Vision](vision.md)
2. [Principles](principles.md)
3. [Architecture](architecture.md)
4. this codebase map
5. [Security model](security-model.md)
6. [Architecture Decision Records](adr/README.md)
7. [Contributing](../CONTRIBUTING.md)
8. the tests for the subsystem you intend to change

Tests are intentionally part of the architecture documentation: they show the
supported behavior more precisely than prose alone.
