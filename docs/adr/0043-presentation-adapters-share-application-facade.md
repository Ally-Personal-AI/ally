# ADR 0043: Presentation adapters share a UI-neutral application facade

**Status:** Accepted

## Context

Ally's CLI was the first executable interface and historically composed several
daily-use workflows directly. A desktop or mobile interface must not reproduce
that composition independently, shell out to the CLI, or become the owner of
conversation grounding, memory correction, model selection, or other domain
semantics.

Duplicating composition across presentation layers would create privacy and
behavior drift. In particular, private chat must continue to use the same active
validated runtime selection, scoped instructions, memory/knowledge grounding,
and durable conversation semantics regardless of interface.

## Decision

Ally introduces a UI-neutral `ally.application` facade over existing
Ally-owned domain/store/runtime contracts.

The application layer:

- exposes typed, serializable request/result models;
- contains no argparse, terminal input, or printing;
- depends on store protocols rather than SQLite implementations;
- resolves model inference through the existing validated inference-target
  boundary;
- reuses existing deterministic memory, knowledge, instruction, and runtime
  behavior; and
- adds no new permission or execution authority.

Concrete default construction lives in the separate `ally.composition` edge.
That module may know about SQLite and the current OpenAI-compatible local
provider because its purpose is dependency assembly, not reusable domain logic.

CLI and future desktop/mobile interfaces are peer presentation adapters over
these shared services.

## Consequences

Chat, conversation inspection, memory management, reviewable memory proposals,
and personal-knowledge operations can be called directly by a local UI without
shelling out to a subprocess.

Future presentation layers should extend the application facade or underlying
domain services rather than reimplementing workflow composition.

The application package is statically checked to prevent terminal presentation
logic and remains subject to the existing architecture rule preventing imports
from `ally.commands` or concrete SQLite storage.
