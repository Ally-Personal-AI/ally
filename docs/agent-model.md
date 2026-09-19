# Agent Model

Ally's agent runtime is introduced incrementally. Reliability, authorization,
and persisted state precede model-driven autonomy.

A task lifecycle is:

```text
goal
  -> plan
  -> persisted task + ordered steps
  -> act through ToolExecutor
  -> observe execution result
  -> verify independently
  -> continue / wait for approval / fail
  -> retry only when explicitly reset
```

## Current implementation

A `TaskPlan` contains a goal and ordered tool steps. Plans can currently be
created from explicit JSON. Model-based planning is deliberately deferred.

Task and step state live in SQLite behind the `TaskStore` contract. Tasks can
therefore survive process restarts.

Every tool step uses the same permissioned `ToolExecutor` used by direct tool
invocation. Tasks cannot bypass policy or audit.

Verification is a separate interface. The initial verifier confirms successful
tool execution; future tools and skills can provide stronger domain-specific
verification without changing the task state machine.

Approval-required steps stop the task in `waiting_approval`. Failed steps stop
the task in `failed`. Neither condition is silently retried.

## Principles

- Plans are durable state, not ephemeral prompt text.
- Long-running tasks must survive process restarts.
- Tool execution is permission checked outside the model.
- Important actions produce audit records.
- Verification is distinct from execution.
- Recovery paths are explicit and inspectable.
- Failed actions are never silently repeated.
- Model planning must produce data consumed by this runtime; it does not own execution.

Greater autonomy is earned through measured reliability.
