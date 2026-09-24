# Ally macOS Desktop

This Swift package is the first native Ally desktop presentation surface. It includes conversation/chat, searchable provenance-aware memory management, local knowledge detail/search/text ingestion, and persisted task detail with exact one-step approval and failed-step retry.

It depends on the local `ally-desktop-bridge` helper and never reimplements Ally
Core policy, persistence, grounding, or model-selection logic.

For development from the repository root:

```bash
uv sync --locked --extra dev
export ALLY_DESKTOP_BRIDGE="$(pwd)/.venv/bin/ally-desktop-bridge"
swift run --package-path desktop/macos AllyDesktop
```

Run native protocol/unit checks with:

```bash
swift test --package-path desktop/macos
```

See `docs/desktop-shell.md` for the architecture, privacy boundary, current
scope, and release-packaging direction.
