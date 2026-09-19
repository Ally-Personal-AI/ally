# Isolated Skill Execution

This document describes the first executable-skill boundary.

## Manifest

A Python skill is executable only when both fields are present:

```toml
id = "example.echo"
name = "Echo"
version = "1.0.0"
description = "Return validated JSON."
entrypoint = "skill_code:run"
execution = "python_subprocess_v1"
```

The callable receives one JSON object and must return a JSON value:

```python
def run(data):
    return {"echo": data["value"]}
```

An `entrypoint` without `execution` remains non-executable.

The V1 subprocess mode intentionally rejects `required_tools`,
`optional_tools`, and skill `config`. No Ally capabilities are injected into
the child process.

## Lifecycle

Install and explicitly enable the package:

```bash
uv run ally skills install ./example-skill
uv run ally skills enable example.echo 1.0.0
```

Run it with an explicit JSON object:

```bash
uv run ally skills run example.echo 1.0.0 \
  --input '{"value":"hello"}'
```

Inspect payload-free execution history:

```bash
uv run ally skills audit
```

## Execution boundary

The parent launches a separate interpreter using `-I -S`.

The child receives:

- a minimal environment;
- the installed skill directory as working directory;
- the package root and validated entrypoint as runner arguments;
- one bounded JSON request on stdin.

It does **not** receive Ally tools, secret values, database paths, model
providers, configuration objects, memory, knowledge documents, or other Core
objects.

Only standard-library imports and modules from the installed skill package are
available by default.

## Protocol and limits

Current defaults:

- input: at most 64 KiB of standard JSON;
- stdout: at most 64 KiB;
- stderr: at most 64 KiB;
- execution timeout: 5 seconds;
- configurable timeout: 1–60 seconds.

Python `print()` output produced while importing/running the skill is
discarded by the worker. Native writes that contaminate stdout/stderr fail the
protocol. A skill result is accepted only after strict response validation.

On POSIX, timeout/output termination targets the child process group. Platform
behavior remains best-effort until stronger OS sandbox integrations exist.

## Audit and privacy

Execution audit records deliberately exclude:

- request input;
- result payload;
- stdout/stderr;
- exception messages.

Built-in Python exception class names may be retained. Arbitrary custom skill
exception class names are normalized to `SkillError`.

## What this does not protect against

A separate process is not a security boundary equivalent to a container,
sandbox profile, VM, or separate OS account.

A skill still runs with the operating-system permissions of the user launching
Ally. Standard-library code can potentially read/write accessible files or open
network connections.

Do not execute untrusted skills as if this were hardened sandboxing.

Future work may add:

- signed packages/trust policy;
- OS-specific sandbox profiles;
- filesystem/network policy;
- CPU/memory quotas;
- dependency environments;
- mediated tool requests routed through Ally policy.

Those layers must build on this process/protocol boundary rather than bypass it.
