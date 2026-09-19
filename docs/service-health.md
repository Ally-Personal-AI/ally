# Service Health and Readiness

`ally service health` is designed for humans, tests, and future operating-
system service managers.

It is deliberately safe to run when the installation may be partially
initialized or damaged.

## Commands

Human-readable:

```bash
uv run ally service health
```

Machine-readable:

```bash
uv run ally service health --json
```

Exit codes:

| Code | Status | Meaning |
| --- | --- | --- |
| 0 | healthy | every readiness check is `ok` |
| 1 | degraded | no errors, but at least one warning |
| 2 | unhealthy | at least one readiness check is an error |

## Stable checks

The initial check IDs are:

- `config.file`
- `database.core`
- `database.schema`
- `service.lifecycle`
- `database.runtime`
- `runtime.leases`

Consumers should key automation on the stable ID and severity rather than
parsing the human summary.

## Schema compatibility

Health compares the persisted ordered `(version, name)` migration history with
the migration sequence compiled into the running Ally version.

An older database is supported for inspection when its history is an **exact
prefix**. That produces a warning; it does not cause health to migrate the
database.

Unknown future migrations, gaps, or renamed historical migrations are errors.

## Adding a health check

A contributor adding a readiness check must preserve all of these properties:

1. **Read-only.** Do not initialize, migrate, repair, or write state.
2. **No network dependency.** Health must work offline.
3. **Safe summaries.** Never include arbitrary exception text or user data.
4. **Deterministic severity.** Equivalent local state must produce equivalent
   severity.
5. **Bounded work.** Health is an operator/readiness probe, not a deep repair
   or evaluation workflow.
6. **Test non-mutation.** Missing files and empty databases must remain
   unchanged after the check.

If a subsystem needs repair or migration, expose that as a separate explicit
operation. Do not hide it inside health.
