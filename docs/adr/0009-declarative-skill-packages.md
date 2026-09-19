# ADR 0009: Skills declare capabilities before execution

**Status:** Accepted

## Context

Skills are intended to compose tools and workflows without modifying Ally Core.
A skill package must therefore be understandable and auditable before any of
its executable code is imported.

## Decision

Every skill package begins with a `skill.toml` manifest using a versioned
schema. The manifest declares identity, version, description, optional Python
entrypoint, required/optional tool names, and configuration fields.

Loading a skill validates only data. Loading a manifest does not import its
entrypoint or execute skill code.

Tool dependencies are capability names, not direct implementation imports.
The tool registry and permission policy remain authoritative.

## Consequences

Ally can inspect, validate, catalog, and eventually sign or distribute skill
packages without executing them. Future schema versions can evolve explicitly.
A skill cannot grant itself permissions merely by declaring a dependency.
