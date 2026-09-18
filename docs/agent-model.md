# Agent Model

Ally's agent runtime will be introduced incrementally.

A reliable task lifecycle is:

```text
goal -> plan -> retrieve -> act -> observe -> verify -> recover/report
```

## Principles

- Plans are state, not ephemeral prompt text.
- Long-running tasks must survive process restarts.
- Tool execution is permission checked outside the model.
- Important actions produce audit records.
- Verification is distinct from execution.
- Recovery paths are designed rather than improvised.

Greater autonomy is earned through measured reliability.
