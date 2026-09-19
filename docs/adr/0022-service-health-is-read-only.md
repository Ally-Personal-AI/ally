# ADR 0022: Service health checks are read-only

**Status:** Accepted

## Context

Future always-on Ally service wrappers need a stable readiness signal before
invoking work or reporting operational health.

Health diagnostics must not repair, migrate, initialize, or otherwise change
the system they are inspecting. A command called "health" should be safe to run
from monitoring software.

## Decision

Ally exposes a structured read-only service health report.

Initial checks cover:

1. non-secret configuration validity;
2. personal SQLite database integrity and migration compatibility;
3. ephemeral runtime service database integrity and lease counts.

Status levels are:

- `ok`
- `warning`
- `error`

Overall states are:

- `healthy`: all checks are ok;
- `degraded`: at least one warning and no errors;
- `unhealthy`: at least one error.

A missing config file is healthy because Ally has safe built-in defaults.

A missing personal database is degraded rather than initialized. Existing
personal databases are opened in SQLite read-only mode and checked with
`PRAGMA quick_check`, `PRAGMA foreign_key_check`, and the
`ally_schema_migrations` history.

The applied migration history must be an exact prefix of Ally's known
version/name sequence. An older supported prefix is degraded; current schema is
healthy; gaps, renamed migrations, or future/unsupported histories are errors.

The runtime service database is inspected separately. Its absence is healthy;
it is disposable coordination state. Active and expired lease counts are
informational.

Health checks do not contact model providers, network services, or external
integrations and do not expose arbitrary exception messages.

## Consequences

OS service managers and monitoring can invoke the same health command without
causing hidden migrations or first-run side effects.

Operational readiness remains distinct from user-work status such as pending
tasks, notifications, or source observations.
