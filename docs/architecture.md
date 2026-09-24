# Architecture

## Core rule

The LLM is a component inside Ally. Ally is not an application wrapped around a
single LLM.

Models, databases, operating-system services, and external integrations are
replaceable implementations behind Ally-owned boundaries.

## Current dependency shape

The repository now separates interface/composition code, reusable domain/runtime
code, and concrete adapters.

```text
CLI / future UI
      |
      v
commands / composition / diagnostics
      |
      v
runtime + service workflows
      |
      v
domain capabilities and Ally-owned protocols
      |
      +--------------------+
      |                    |
      v                    v
storage contracts      model contracts
      |                    |
      v                    v
SQLite adapters        provider adapters
```

Major domain capabilities include conversations, memory, knowledge, context,
tools, tasks, events, scheduling, event sources, attention delivery, planning,
and skills.

See [Codebase Map](codebase-map.md) for package-by-package ownership.

## Dependency direction

Higher-level interfaces compose lower-level Ally capabilities. Reusable Core
packages must not depend upward on CLI/command handlers or downward on concrete
SQLite implementations.

For example:

```text
Ally runtime -> ModelProvider -> OpenAI-compatible / MLX / llama.cpp / future
domain store protocol <- SQLite implementation
```

The concrete dependency direction is protected by
`tests/test_architecture_boundaries.py`.

The test is intentionally small. It protects durable layer boundaries without
trying to freeze every internal package relationship.

## Composition edges

Some packages intentionally sit at the edge of Core:

- `commands/` assembles dependencies for human-facing operations;
- `diagnostics/` inspects physical runtime state read-only;
- `portability/` moves/validates the concrete user-owned database;
- `service/macos_launchd.py` is an opt-in OS composition adapter around the
  bounded service command;
- `storage/` contains concrete persistence implementations.

Those edges may know about SQLite. Domain/runtime packages should depend on
Ally-owned protocols instead.

## Model fabric

Model runtimes sit behind provider abstractions. The current executable provider
uses an OpenAI-compatible local HTTP endpoint; future MLX, llama.cpp, Ollama,
CUDA, and other runtimes can be added without changing memory, tasks, tools, or
identity state.

For production selection, candidate qualification is converted into an immutable
[Validated Runtime Profile](validated-runtime-profiles.md). Future UI/runtime
composition should consume those profiles rather than arbitrary endpoint/model
pairs, preserving the evidence boundary between experimentation and approved
daily-use inference. Qualified profiles can be installed into the
[Runtime Profile Catalog](runtime-profile-catalog.md); active selection is
hash-bound to the exact installed profile and exposed through one reusable
resolver.

Long-running candidate qualification is coordinated by
[Validation Sessions](validation-sessions.md). Session manifests store only the
plan; status is always re-derived from live readiness and the exact evidence
artifacts, so orchestration never becomes an alternate authority layer.

```text
Ally Core
   |
   v
ModelProvider
   |
   +-- OpenAI-compatible local runtime
   +-- MLX (future direct adapter)
   +-- llama.cpp (future direct adapter)
   +-- other future runtimes
```

Hardware-specific choices remain evidence-driven and are intentionally deferred
until first-machine validation. Private user data is not eligible for external
model inference; see [Private Intelligence Boundary](private-intelligence-boundary.md).

## Persistence

User-owned durable state is stored locally. Domain packages expose persistence
contracts; `storage/sqlite/` implements those contracts with versioned
migrations.

Disposable runtime coordination state is kept separate from portable personal
state where appropriate.

## Security boundaries

Security decisions are explicit architecture, not implementation detail:

- private inference is loopback-only in the current trust domain and has no remote override;
- external model access is reserved for bundled synthetic/public evaluation data;
- tool execution passes through deterministic policy;
- model planning/memory extraction produce proposals, not automatic authority;
- skill installation is non-executing;
- executable skills run outside the Ally Core interpreter;
- credentials remain outside ordinary configuration;
- service health/readiness is read-only;
- private model inference never uses the external egress boundary; and
- future external tools use typed, adapter-owned field classifications and
  payload-minimized egress audit.

See [Security Model](security-model.md),
[Private Intelligence Boundary](private-intelligence-boundary.md),
[Controlled External Egress](controlled-egress.md), and the ADR log for exact
decisions.

## Initial runtime and interfaces

The first implementation is Python 3.12. The primary executable interface is the
`ally` CLI.

A future web/desktop interface should call the same Core/runtime boundaries
rather than move domain logic into presentation code.

## Repository strategy

Ally begins as a monorepo. Components should only be split into independent
repositories when independent release, ownership, or distribution requirements
justify it.
