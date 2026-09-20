# Contributing to Ally

Ally is early. Contributions should preserve the project's local-first,
user-owned architecture.

## Start here

Before changing a subsystem, read:

1. [Vision](docs/vision.md)
2. [Principles](docs/principles.md)
3. [Architecture](docs/architecture.md)
4. [Codebase Map](docs/codebase-map.md)
5. [Security Model](docs/security-model.md)
6. [Architecture Decision Records](docs/adr/README.md)

Then read the tests for the subsystem you plan to change.

## Development

```bash
uv sync --locked --extra dev
uv run ally doctor
uv run ruff check .
uv run pyright
uv run pytest
uv run ally eval run
```

## Reproducible dependencies

`uv.lock` is committed and is the authoritative dependency resolution used by
CI and first-machine validation.

- Use `uv sync --locked --extra dev` for ordinary development and validation.
- If `pyproject.toml` changes dependencies, run `uv lock` and commit the
  resulting lockfile change in the same pull request.
- Do not hand-edit `uv.lock`.
- Dependency update pull requests must pass Linux quality, macOS portability,
  and both distribution jobs before merge.

## Package placement

Keep dependency direction clear:

- CLI parsing belongs in `src/ally/cli.py`.
- Human-facing composition/formatting belongs in `src/ally/commands/`.
- Reusable domain/runtime behavior belongs in the relevant Core package.
- Database/vendor/OS implementations belong behind Ally-owned interfaces.
- Do not import `ally.commands` or `ally.cli` from reusable Core packages.
- Do not import `ally.storage.sqlite` from domain/runtime packages.

CI enforces these major boundaries in
`tests/test_architecture_boundaries.py`.

If a boundary genuinely needs to change, update the architecture documentation
and record the reason in an ADR rather than adding a one-off test exception.

## CI platforms

The primary Ubuntu job runs lint, strict typing, coverage tests with an 80%
minimum project-wide coverage gate, and the frozen behavioral evaluation suite.
All CI jobs install the exact committed dependency graph with
`uv sync --locked`.

A separate macOS smoke job installs the project, runs the full test suite, and
runs the same frozen core evaluations. It exists to catch operating-system
portability regressions without duplicating coverage/lint/type work.

Linux and macOS distribution jobs also build and install the actual package
and exercise synthetic workflows outside the checkout. See below for the
same check locally.

Passing macOS CI does not replace the dedicated Apple Silicon validation
runbook or provide evidence about local-model performance.

The separate read-only security workflow audits the locked runtime dependency
graph and statically checks GitHub workflow definitions. Run the same checks
locally with:

```bash
uv sync --locked --extra security
uv export --locked --no-dev --no-emit-project --output-file /tmp/ally-runtime-requirements.txt
uv run pip-audit --strict --require-hashes --disable-pip --progress-spinner off --requirement /tmp/ally-runtime-requirements.txt
uv run zizmor --offline --strict-collection .github
```

See [Security Policy](SECURITY.md) for finding triage and exception rules.

## Clean-install verification

Run this before changing packaging, bundled resources, or installed command
behavior:

```bash
uv run --locked --group build python scripts/check_distribution.py
```

The check builds an sdist, builds a wheel from that sdist, verifies that every
source module and frozen JSONL fixture is present, and installs the wheel in a
fresh temporary environment. The build backend comes from the locked `build`
dependency group. Runtime dependencies are exported from `uv.lock` and installed
with required hashes; the fresh environment contains no development/build tools.

From a temporary directory outside the checkout, an isolated Python interpreter
tests the installed console entry point, bundled evaluations, chat/resume over
real loopback HTTP, persistent memory and knowledge, read-only tasks, service
health, a skill subprocess, and backup/restore. Proxy environment settings are
deliberately present to check that local inference stays local. Stateful CLI
commands run in separate processes; only OS application-directory discovery is
redirected to temporary synthetic state on both platforms. No real Ally data or
Keychain entries are read or changed.

Downloads require package-index access; inference uses a synthetic local server.
Temporary installations, data, and archives are removed when the check exits.
This verifies distribution and integration behavior, not model quality or
dedicated-hardware performance.

The `.gitignore` exceptions for `src/ally/models/`, `src/ally/runtime/`, and
`src/ally/secrets/` are intentional: these are source packages. Keep the broader
private-data exclusions; removing the source exceptions silently drops code
from release archives even when editable development installs work.

## Database changes

Existing migrations in `src/ally/storage/sqlite/schema.py` are append-only. Add the
next consecutive migration instead of editing one that has already reached main.
Migration statements must not commit or manage transactions; `SQLiteDatabase`
owns that boundary.
`tests/test_database_recovery.py` pins historical definitions and exercises every
supported prefix, rollback after failed DDL, concurrent startup, and restore
publication. Do not regenerate historical fingerprints to make a changed migration
pass. See [database recovery](docs/database-recovery.md) and
[ADR 0029](docs/adr/0029-atomic-database-recovery.md).

## Pull requests

- Keep changes focused.
- Add or update tests for behavior changes.
- Keep strict typing and lint clean.
- Run the behavioral eval suite when behavior/policy changes.
- Record significant or hard-to-reverse architectural decisions as ADRs.
- Update contributor-facing docs when a public package/CLI boundary changes.
- Never include personal user data in fixtures, logs, examples, or commits.
- Prefer small Ally-owned interfaces around replaceable infrastructure.
- Keep privacy/security failures fail-closed rather than silently permissive.

## Data discipline

Personal information, credentials, local memory databases, private documents,
runtime logs containing private data, model weights, and generated indexes do
not belong in the repository.

Tests and examples must use synthetic or appropriately licensed public data.

## Review checklist

Before merging, verify:

- the code has a clear package owner;
- no new upward dependency was introduced;
- concrete infrastructure remains behind a boundary;
- error/audit paths do not copy private payloads unnecessarily;
- durable-state changes have migration and backup/restore coverage when needed;
- user-facing behavior is documented where appropriate.

By contributing, you agree that your contributions are licensed under the
repository license.
