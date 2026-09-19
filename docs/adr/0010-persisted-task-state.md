# ADR 0010: Agent tasks are persisted state machines

**Status:** Accepted

## Context

Long-running Ally tasks must survive process restarts and must not rely on
ephemeral prompt state. Tool execution also has separate authorization and
audit requirements.

## Decision

A task is stored as a durable task record plus ordered step records. The first
step type is a tool invocation. The task runner advances persisted state rather
than holding the plan only in memory.

Execution follows an explicit lifecycle:

```text
plan -> act -> observe -> verify -> continue / wait / fail
```

Tool calls always use the permissioned ToolExecutor. Verification is a separate
interface from execution. Approval-required steps pause the task and can be
resumed with explicit approval. Failed steps remain failed until deliberately
reset for retry.

Model-based planning is not part of this layer. Models may create TaskPlan
objects later, but they do not own persistence, authorization, or execution.

## Consequences

Tasks can be resumed after restart and inspected independently of any model.
The deterministic executor can be tested with synthetic tools before real
agent planning is enabled.
