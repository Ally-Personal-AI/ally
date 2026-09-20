# ADR 0030: The macOS managed service is explicit and bounded

## Status

Accepted

## Context

Ally's proactive workflow is intentionally a bounded command. A dedicated Mac
needs an operating-system supervisor to invoke that command after login and on
a schedule, but service integration must not turn Core into a daemon or silently
enable background activity during installation.

Launch-agent files are also a security boundary. Shell interpretation, relative
paths, silent replacement of an existing definition, or deletion of a modified
definition could execute the wrong program or destroy user-managed state.

## Decision

Ally provides one opt-in macOS launch-agent adapter with a fixed label and a
deterministic plist. The definition:

- invokes the absolute current Python interpreter directly, without a shell;
- runs `-m ally.cli service cycle --json`, preserving the bounded cycle;
- runs at login and at a fixed 60-second interval;
- sends stdout and stderr to explicit files under Ally's data directory; and
- applies a restrictive process umask.

Installing Ally does not install the launch agent. Only the explicit
`ally service managed install` command may publish and bootstrap it.

Publication uses same-directory staging and no-replace hard-link creation. Ally
refuses symlinks and any existing, changed, or malformed definition. Uninstall
also requires the installed bytes to match the definition Ally would generate.
Launchctl is executed directly with an argument vector and errors do not include
captured output.

Inspection is available without mutation on every platform. Other lifecycle
mutations fail closed outside macOS. Real login, restart, locked-state, failure-
recovery, and log-retention behavior require dedicated-machine acceptance.

## Consequences

The launch-agent behavior can be unit-tested and distribution-tested before the
hardware arrives, while activation remains a deliberate user choice. The Python
environment used at installation must remain at the recorded absolute path.
Changing environments requires uninstalling with the old environment before
installing from the new one.

The OS supervisor owns recurrence and process supervision. Ally Core retains no
sleep loop or daemon lifecycle, so future service adapters can reuse the same
bounded command.
