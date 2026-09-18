# ADR 0004: SQLite is the first local persistence adapter

**Status:** Accepted

## Context

Ally needs durable local state for conversations, memory, and knowledge metadata. The project also needs a zero-administration default suitable for a single-user local installation.

## Decision

SQLite is the first persistence implementation.

Domain code depends on Ally-owned storage contracts rather than SQLite APIs. Database schema changes are versioned through explicit migrations. The database lives in the operating system's Ally data directory, outside the source repository.

## Consequences

A new Ally installation requires no database service. Backups can include a small number of local files. Future storage engines remain possible because higher-level code does not depend directly on SQLite.

SQLite is an implementation choice for local persistence, not the canonical representation of Ally's domain model.
