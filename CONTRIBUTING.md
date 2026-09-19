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
uv run ally eval run evals/cases/core.jsonl
```

## Reproducible dependencies

`uv.lock` is committed and is the authoritative dependency resolution used by
CI and first-machine validation.

- Use `uv sync --locked --extra dev` for ordinary development and validation.
- If `pyproject.toml` changes dependencies, run `uv lock` and commit the
  resulting lockfile change in the same pull request.
- Do not hand-edit `uv.lock`.
- Dependency update pull requests must pass both Linux quality CI and macOS
  portability CI before merge.

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

The primary Ubuntu job runs lint, strict typing, coverage tests with a 70%
minimum project-wide coverage gate, and the frozen behavioral evaluation suite.
Both CI jobs install the exact committed dependency graph with
`uv sync --locked`.

A separate macOS smoke job installs the project, runs the full test suite, and
runs the same frozen core evaluations. It exists to catch operating-system
portability regressions without duplicating coverage/lint/type work.

Passing macOS CI does not replace the dedicated Apple Silicon validation
runbook or provide evidence about local-model performance.

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
