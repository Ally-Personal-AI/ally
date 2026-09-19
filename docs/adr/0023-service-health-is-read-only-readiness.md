# ADR 0023: Service health is structured read-only readiness

**Status:** Accepted

## Context

ADR 0022 introduced read-only health around portable lifecycle history and the
separate ephemeral coordination lease. A single coarse status is not enough for
operators or future service managers to distinguish:

- a fresh but not-yet-initialized installation;
- an older supported database schema;
- invalid or future migration history;
- malformed configuration;
- a corrupt core or runtime database;
- ordinary expired leases;
- an orphaned `running` lifecycle record.

Health must also be safe to call precisely when state may be damaged. It must
not repair, migrate, initialize, contact models, or leak arbitrary exception
text.

## Decision

`ally service health` is a deterministic **readiness** report composed of
explicit checks.

Each check has:

- a stable check ID;
- severity: `ok`, `warning`, or `error`;
- a bounded, predetermined summary safe for logs and service managers.

Overall status is derived mechanically:

- any `error` -> `unhealthy`;
- otherwise any `warning` -> `degraded`;
- otherwise -> `healthy`.

CLI exit codes mirror that order:

- `0`: healthy;
- `1`: degraded;
- `2`: unhealthy.

### Configuration

An existing config is validated with the normal strict `AllyConfig` schema.
A missing config is a warning because safe defaults exist. Invalid or unreadable
config is an error.

Health never initializes a missing config.

### Core database

The database is opened read-only and checked with SQLite `quick_check`.

Migration history is valid only when ordered `(version, name)` rows are an
exact prefix of the migrations compiled into the current Ally build.

- current exact history: `ok`;
- older exact supported prefix: `warning`;
- gaps, changed names, or future/unknown migrations: `error`;
- missing database or an empty uninitialized SQLite file: `warning`;
- tables without Ally migration history: `error`.

Health never runs migrations.

### Runtime coordination database

The disposable runtime database is opened separately and read-only.

A missing runtime database is a warning. Corruption, missing lease schema, or
invalid lease timestamps are errors.

Active and expired lease counts are informational and do not change readiness by
themselves.

### Lifecycle consistency

A completed failed/degraded/interrupted latest cycle is a warning, not structural
corruption.

A portable `running` lifecycle record is valid only while the
`proactive-cycle` runtime lease is active. A running record without that lease
is an error.

### Privacy and side effects

Readiness must never:

- create or migrate config or databases;
- contact model providers or other network services;
- execute tools or skills;
- persist diagnostics;
- include credentials, personal payloads, arbitrary exception messages, prompt
  text, model output, or document content in check summaries.

## Consequences

Future launchd/systemd/Windows service managers can use one stable machine-
readable readiness surface without granting health checks mutation authority.

This ADR refines the health-classification portion of ADR 0022; the portable
lifecycle and ephemeral lease decisions remain unchanged.
