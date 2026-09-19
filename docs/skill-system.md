# Skill System

Tools expose atomic capabilities. Skills compose capabilities, policies,
prompts, knowledge, configuration, and workflows into reusable behavior.

## Package boundary

Every skill package starts with a `skill.toml` manifest. Ally parses and
validates that manifest as data before any executable skill code may run.

The manifest schema includes:

- schema version;
- stable skill ID;
- display name and version;
- description;
- optional Python entrypoint;
- optional execution mode;
- required/optional tool declarations for non-executing/declarative skill use;
- typed configuration fields;
- secret markers for configuration values that must not be treated as ordinary data.

Unknown manifest fields are rejected.

A manifest can describe capability requirements. It cannot grant itself
permission.

## Declarative example

```toml
schema_version = 1
id = "example.daily-briefing"
name = "Daily Briefing"
version = "0.1.0"
description = "Build a local morning briefing."
required_tools = ["calendar.read"]
optional_tools = ["weather.read"]

[config.timezone]
type = "string"
description = "IANA timezone used for the briefing."
required = true
```

Tool availability and permissions remain controlled by Ally's tool registry and
policy engine.

## Local installation

Ally installs an explicit local package into Ally-owned application data:

```text
skills/<skill-id>/<version>/
```

Installation is non-executing. Before copying, Ally:

- validates the manifest;
- rejects symbolic links and non-regular package entries;
- rejects the reserved Ally installation metadata filename;
- validates declared required tools against the current runtime registry;
- validates skill ID/version before using them as filesystem path components.

Installed packages are disabled by default. Only one version of a skill ID may
be enabled at a time.

```bash
uv run ally skills install ./skill
uv run ally skills installed
uv run ally skills enable <skill-id> <version>
uv run ally skills disable <skill-id> <version>
uv run ally skills uninstall <skill-id> <version>
```

## Executable Python skills

Execution requires a second explicit manifest opt-in:

```toml
schema_version = 1
id = "example.echo"
name = "Echo"
version = "1.0.0"
description = "Return JSON."
entrypoint = "skill_code:run"
execution = "python_subprocess_v1"
```

An entrypoint without `execution` does not make a package runnable.

The first execution mode intentionally exposes **no Ally tools and no skill
configuration**. Its manifest cannot declare required/optional tools or config.
Future mediated capabilities must enter through Ally's normal permission system.

An enabled installed skill may be run explicitly:

```bash
uv run ally skills run example.echo 1.0.0 \
  --input '{"value":"hello"}'
uv run ally skills audit
```

Ally Core never imports installed executable skill modules. A separate Python
interpreter executes the entrypoint through a bounded, versioned JSON protocol.

See [Isolated Skill Execution](skill-execution.md) for limits, audit behavior,
and the security model.

## Security boundary

`python_subprocess_v1` provides process and protocol isolation, not a hardened
operating-system sandbox.

The child receives no Ally tool handles, secret store, configuration object,
database path, memory/document handles, or model provider. It runs with
`python -I -S`, a minimal environment, the installed package as working
directory, bounded I/O, and a timeout.

However, it still normally runs as the same OS user as Ally and may use
standard-library APIs to reach filesystem/network resources that user can
access. Untrusted code must not be treated as safely sandboxed.

## Audit

Execution audit is deliberately payload-free. It records identifiers, status,
timestamps/duration, exit code, and a safe error class.

It does not persist input, result data, stdout, stderr, or exception messages.

## Current scope

Implemented:

- manifest validation;
- dependency validation;
- local installation/enable/disable/uninstall;
- explicit Python subprocess execution;
- bounded JSON protocol;
- payload-free execution audit.

Deferred:

- signed packages and trust policy;
- third-party dependency environments;
- mediated skill-to-tool requests;
- filesystem/network policy;
- hardened OS sandboxing;
- remote registry/marketplace;
- generated-skill sandbox/test/install workflow.

Those future layers must build on these package/install/process boundaries rather
than bypass them.
