# ADR 0025: Package dependency direction is tested

**Status:** Accepted

## Context

Ally's deterministic core has grown from a few packages into multiple domains:
memory, knowledge, tools, tasks, proactivity, skills, storage, diagnostics, and
model-provider adapters.

Without an explicit guardrail, convenient imports can gradually invert the
architecture—for example, domain logic importing CLI handlers or reaching
directly into SQLite. Those shortcuts make later interfaces, storage engines,
and platform ports harder to build.

A complete static dependency graph would be brittle at this stage. The project
needs a small set of durable rules that match the current architecture.

## Decision

Ally documents the live package map in `docs/codebase-map.md` and enforces
three dependency properties with standard-library AST tests:

1. reusable/core packages do not import `ally.commands`;
2. reusable packages do not import `ally.cli`;
3. core/domain packages do not import the concrete
   `ally.storage.sqlite` implementation.

The SQLite rule allows explicit infrastructure/composition edges:

- `commands`
- `diagnostics`
- `portability`
- `storage`

Domain code may depend on Ally-owned storage protocols and models. Concrete
adapters depend on those contracts, not the other way around.

The test deliberately does **not** encode every allowed package-to-package edge.
A new architectural rule should be added only when it represents a durable,
easy-to-explain property rather than current incidental structure.

## Consequences

A contributor receives immediate CI feedback when a change crosses a major
layer in the wrong direction.

Ally remains free to refactor internal domain collaboration without constantly
rewriting a fragile dependency matrix.

Future interfaces, storage engines, and provider implementations can reuse Core
without importing the CLI or undoing SQLite coupling.
