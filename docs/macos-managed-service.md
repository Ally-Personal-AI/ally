# Managed macOS service

Ally's launch-agent adapter makes the bounded proactive cycle recurrent without
putting daemon behavior into Ally Core. It is present but disabled until the
user explicitly installs it.

## Inspect before installing

```bash
ally service managed inspect
```

This prints the complete deterministic plist and never writes a file or calls
`launchctl`. It works on Linux CI as well as macOS.

Review these absolute paths in the output:

- the Python interpreter at the start of `ProgramArguments`;
- `StandardOutPath`; and
- `StandardErrorPath`.

The interpreter must be the stable environment intended to run Ally. The agent
does not activate a virtual environment or search `PATH`.

## Lifecycle

Run these as the macOS login user, not with `sudo`:

```bash
ally service managed install
ally service managed status --json
ally service managed stop
ally service managed start
ally service managed uninstall
```

Install publishes `~/Library/LaunchAgents/ai.ally.proactive-service.plist` only
when the destination is absent, then bootstraps it into the current GUI user's
launchd domain. Repeating install is safe when the exact definition is already
present. A different file or symlink is never overwritten.

Uninstall first unloads the agent and then removes the plist. It refuses to
remove a definition whose bytes no longer match Ally's expected definition.
Logs and personal data are retained.

## Dedicated-machine acceptance

The implementation and mocked lifecycle are hardware-independent. Before
calling the service production-ready, verify on the dedicated Mac:

1. inspect and install as the intended login user;
2. confirm a successful cycle and health report;
3. log out and in, then confirm the agent loads and cycles resume;
4. restart the Mac and repeat the check;
5. exercise a cycle failure and confirm later cycles recover;
6. confirm overlapping invocations are rejected by the runtime lease;
7. inspect stdout/stderr growth and choose a log-retention policy; and
8. uninstall and confirm the agent is unloaded while data and logs remain.

Record the exact Ally version, Python path, macOS version, commands, timestamps,
and observed results in the hardware acceptance evidence.
