# Contributing to Ally

Ally is early. Contributions should preserve the project's local-first, user-owned architecture.

## Development

```bash
uv sync --extra dev
uv run ally doctor
uv run ruff check .
uv run pyright
uv run pytest
```

## Pull requests

- Keep changes focused.
- Add or update tests for behavior changes.
- Record significant architectural decisions as ADRs.
- Never include personal user data in fixtures, logs, examples, or commits.
- Prefer small Ally-owned interfaces around replaceable infrastructure.

By contributing, you agree that your contributions are licensed under the repository license.
