# ADR 0032: User instructions compose by explicit scope

**Status:** Accepted

## Context

A single global instruction profile cannot express the different working
conventions needed across projects, conversations, tasks, and one-off sessions.
Replacing the global text with whichever instruction is most specific would
also make behavior difficult to inspect and could silently discard durable user
preferences.

## Decision

Durable user instructions compose in this fixed order:

```text
global -> project -> conversation -> task
```

A caller may append an ephemeral session instruction after durable scopes.
Session instructions are never persisted.

Durable project, conversation, and task profiles require explicit scope keys.
Profiles may be disabled without deletion. Composition includes only enabled
profiles and renders scope provenance into model context.

Instruction scopes affect behavior only. They do not modify capability,
privacy, audit, or execution authority.

## Consequences

The same durable preferences survive model replacement while more-specific
working contexts can refine behavior predictably. Future interfaces can display
and edit the exact contributing scopes instead of reconstructing an opaque
system prompt.
