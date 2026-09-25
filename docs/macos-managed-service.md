# Managed macOS service

Ally's historical Python launch-agent adapter remains available for CLI
compatibility and migration testing. It is **not** the production scheduler for
the signed desktop app.

The accepted desktop path uses `SMAppService.mainApp` for explicit
launch-at-login registration and keeps modern `UNUserNotificationCenter`
delivery inside the signed `ai.ally.personal` application identity.

## Historical launch-agent contract

The legacy adapter invokes one bounded `ally service cycle --json` every 60
seconds under the label:

```text
ai.ally.proactive-service
```

Its deterministic definition can still be inspected without mutation:

```bash
ally service managed inspect
ally service managed status --json
```

Manual install/start/stop/uninstall commands remain for compatibility and
operator recovery, but new desktop installations should not install this agent.

## Fail-closed desktop migration

Desktop protocol v7 exposes only path-free legacy-service migration state. The
signed app does not receive the plist path or historical Python executable.

A definition is automatically retirable only when:

- it is a regular file, not a symlink;
- its label, interval, run-at-load behavior, process type, I/O priority, umask,
  log paths, and command arguments match Ally's deterministic legacy definition;
- only the first absolute Python executable path differs from the current
  environment, allowing an older Ally install to be recognized safely.

Modified or unrecognized definitions are never removed automatically.

Retirement unloads the exact launchd label, re-validates the recognized file and
its filesystem identity, then unlinks only that same file. A racing replacement
is left in place and migration fails closed.

While any legacy definition remains configured—or its state cannot be verified—
the signed app refuses to enable modern background proactivity and pauses its
automatic proactive loop. The runtime lease remains a second line of defense
against overlapping cycles, not the migration mechanism itself.

## Dedicated-machine acceptance

On the dedicated Mac:

1. inspect `ally service managed status --json` before enabling the signed app;
2. for a clean install, confirm no legacy definition exists and enable Background
   Proactivity through the app;
3. for an upgrade test, install/create the exact historical Ally definition,
   confirm the app detects it, and retire it through the explicit migration UI;
4. alter a synthetic legacy definition and confirm the app refuses automatic
   retirement and pauses background proactivity;
5. confirm `SMAppService.mainApp` enable/disable state tracks Login Items;
6. verify bounded cycles after login and full restart;
7. verify cycle failure recovery and lease rejection of overlap; and
8. confirm migration/removal leaves Ally data and historical logs intact.

For the overall order and stop conditions, start with
[Unified First-Machine Acceptance](hardware/first-machine-acceptance.md).
