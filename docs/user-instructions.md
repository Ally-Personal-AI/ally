# Scoped User Instructions

Ally treats user instructions as private, user-owned state rather than ordinary
application configuration or model identity.

## Scope order

Durable scopes compose from broadest to most specific:

1. `global`
2. `project`
3. `conversation`
4. `task`
5. temporary `session` instructions

More-specific scopes do not delete or silently replace broader scopes. Ally
renders each contribution with its provenance so the effective request context
is inspectable.

The session layer is ephemeral. It is accepted by a caller for one invocation
and is never written to the instruction store.

## Storage

Durable profiles live in the user-owned Ally SQLite database. Each profile is
identified by a scope and scope key. The global profile uses an empty key;
project, conversation, and task profiles require explicit keys.

Profiles can be disabled without deletion. Disabled profiles remain inspectable
and portable but do not participate in resolution.

## CLI

Create global instructions:

```bash
ally instructions set "Prefer concise answers and challenge assumptions."
```

Create a project profile:

```bash
ally instructions set "Use the project's Python conventions." \
  --scope project --key example-project
```

Inspect effective composition:

```bash
ally instructions resolve \
  --project example-project \
  --conversation example-conversation \
  --session "For this response, give extra implementation detail."
```

Temporarily disable a profile:

```bash
ally instructions disable --scope project --key example-project
```

Chat automatically resolves the global profile plus the active conversation
profile. Optional project/task keys and non-persistent session instructions may
also be supplied explicitly.

All resolved instructions are private model context and therefore use only the
private loopback inference provider. They are not eligible for external model
inference.

## Authority boundary

Instruction composition changes model context only. No instruction scope can
grant tools, change privacy policy, bypass audit, authorize an external action,
or alter its own execution authority. Those decisions remain in Ally-owned
deterministic policy.
