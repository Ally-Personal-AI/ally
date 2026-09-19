# ADR 0011: Model-generated plans are untrusted proposal data

**Status:** Accepted

## Context

A capable local model should eventually help decompose goals into executable
steps. Letting model output directly drive tool execution would collapse
planning, authorization, persistence, and action into one unsafe boundary.

## Decision

Model planning produces only validated `TaskPlan` data.

The planning layer:

- receives an explicit goal;
- receives an explicit list of available tool specifications;
- asks the provider for strict JSON;
- validates the JSON as `TaskPlan`;
- requires the returned goal to exactly match the requested goal;
- rejects any tool name that was not explicitly supplied;
- does not create a persisted task;
- does not invoke `ToolExecutor`;
- does not grant approvals or permissions.

A human or later policy-controlled workflow may choose to persist the proposed
plan. Execution remains exclusively inside the existing task runtime and tool
policy boundary.

## Consequences

Planning quality can improve with better local models without increasing the
model's authority. Provider-backed planning evaluations can measure plan shape
and tool selection independently of task execution.
