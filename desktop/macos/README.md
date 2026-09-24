# Ally macOS Desktop

This Swift package is the first native Ally desktop presentation surface. It includes conversation/chat, searchable provenance-aware memory management, local knowledge detail/search/text ingestion, persisted task detail with exact one-step approval and failed-step retry, selection among already-installed validated runtime profiles, a durable Attention Center, and modern macOS notification authorization.

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


## Release bundle foundation

Release builds are designed to run from a stable `Ally.app` identity and an
embedded verified helper. They do not rely on `ALLY_DESKTOP_BRIDGE` or
`PATH`.

After building the Swift release executable and a standalone helper artifact,
assemble the app with:

```bash
python scripts/macos_app_bundle.py assemble \
  --app-executable /absolute/path/to/AllyDesktop \
  --helper /absolute/path/to/ally-desktop-bridge \
  --output /absolute/path/to/Ally.app \
  --source-revision <git-sha> \
  --build-version 1
```

Developer ID signing and notarization use
`scripts/macos_release_signing.py`. Notarization accepts a preconfigured
`notarytool` Keychain profile rather than credential values on the command
line.

See `docs/macos-release-security.md` for the trust and rollback model. The
standalone Python helper artifact and real Developer ID/notarization acceptance
remain pending.
