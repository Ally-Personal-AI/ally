# ADR 0021: Service lifecycle history is payload-free

**Status:** Accepted

## Context

A future always-on Ally process needs a durable answer to operational questions:

- did the last proactive cycle finish;
- did delivery degrade;
- did a cycle raise an exception;
- was a prior cycle abandoned;
- is the local database structurally healthy.

Console logs are not a reliable lifecycle record, and copying event/task payloads
into an observability table would unnecessarily duplicate private data.

## Decision

A thin `ProactiveServiceRunner` wraps the existing bounded
`ProactiveServiceCycle`.

Every attempted cycle receives one persisted lifecycle record containing only:

- run ID;
- lifecycle status;
- requested observation timestamp;
- start/finish timestamps;
- schedule/delivery counts;
- a safe exception class for failed/interrupted runs.

No event payload, prompt, document content, delivery body, arbitrary exception
message, credential, or model output is copied into service lifecycle history.

Lifecycle statuses are:

- `running`
- `succeeded`
- `degraded` (cycle completed but one or more deliveries failed)
- `failed` (cycle raised)
- `interrupted` (an old running lease was recovered)

Only one fresh running cycle may exist. Before starting, the runner recovers
`running` records older than a conservative one-hour stale window as
`interrupted`. A newer running record blocks another cycle instead of being
silently treated as crashed.

Health inspection is local and deterministic. It checks SQLite `quick_check`,
compares applied schema migrations with the code's expected migration set, and
reports the latest lifecycle state. It does not contact a telemetry service.

A healthy database with no lifecycle history is `uninitialized`, not
`healthy`, because no proactive cycle has yet demonstrated execution.

## Consequences

Future launchd/systemd/Windows wrappers can supervise the process while Ally Core
retains portable lifecycle semantics.

Operational history remains useful without becoming a second repository of
personal data.
