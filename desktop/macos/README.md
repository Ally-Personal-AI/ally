# Ally macOS Desktop

This Swift package is Ally's native desktop presentation surface. It includes conversation/chat, searchable provenance-aware memory management, local knowledge detail/search/text ingestion, persisted task detail with exact one-step approval and failed-step retry, validated runtime-profile selection, the durable Attention Center, modern app-owned notification delivery, and explicit launch-at-login control.

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

## App-owned proactivity

The signed app uses bridge protocol v6 for a narrow prepare/ack/complete flow:

- `service.prepare_proactive` returns rendered notification candidates only;
- Swift delivers through `UNUserNotificationCenter` using the deterministic
  delivery key;
- `attention.notification_result` acknowledges only an exact run/event/key
  tuple plus success/failure; and
- `service.complete_proactive` lets Ally compute the terminal lifecycle state
  from durable counters.

Background proactivity is separately opt-in through `SMAppService.mainApp`.
Registration and notification authorization are independent user choices.

The deprecated Python `NSUserNotificationCenter` adapter is not part of the
signed desktop delivery path.


## Release bundle foundation

Release builds are designed to run from a stable `Ally.app` identity and an
embedded verified helper. They do not rely on `ALLY_DESKTOP_BRIDGE` or
`PATH`.

The release CI builds the standalone helper with
`scripts/build_macos_desktop_helper.py`. For a Developer ID release, pass the
same Developer ID Application identity to that helper build so PyInstaller can
sign its embedded binary payload.

After building the Swift release executable and standalone helper, assemble the
app with:

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

See `docs/macos-release-security.md` for the trust and rollback model. Real
Developer ID/notarization and installed-machine acceptance remain pending.
