# Skill System

Tools expose atomic capabilities. Skills compose tools, policies, prompts,
knowledge, configuration, and workflows into reusable behavior.

## Package boundary

Every skill package starts with a `skill.toml` manifest. Ally validates that
manifest before importing any executable skill code.

The initial manifest schema includes:

- schema version
- stable skill ID
- display name and version
- description
- optional Python entrypoint
- required tool names
- optional tool names
- typed configuration fields
- secret markers for configuration values that must not be treated as ordinary data

Unknown manifest fields are rejected.

A manifest can declare that a skill needs a capability. It cannot grant itself
that capability. Tool availability and tool permission remain controlled by the
tool registry and Ally's policy engine.

## Example

```toml
schema_version = 1
id = "example.daily-briefing"
name = "Daily Briefing"
version = "0.1.0"
description = "Build a local morning briefing."
entrypoint = "daily_briefing:run"
required_tools = ["calendar.read"]
optional_tools = ["weather.read"]

[config.timezone]
type = "string"
description = "IANA timezone used for the briefing."
required = true
```

## Local installation

Ally can install an explicit local package into Ally-owned application data:

```text
skills/<skill-id>/<version>/
```

Installation performs data validation only. It never imports the entrypoint.

Before copying, Ally:

- validates the manifest;
- rejects symbolic links and non-regular package entries;
- rejects the reserved Ally installation metadata filename;
- validates declared required tools against the current runtime registry;
- validates skill ID/version before using them as filesystem path components.

Installed packages are disabled by default.

Only one version of a skill ID may be enabled at a time. Enabling one version
automatically disables another enabled version with the same ID.

Uninstall removes only Ally's copied package. The original source directory is
never modified.

Commands:

```bash
uv run ally skills install ./skill
uv run ally skills installed
uv run ally skills enable <skill-id> <version>
uv run ally skills disable <skill-id> <version>
uv run ally skills uninstall <skill-id> <version>
```

## Current scope

Ally can load, inspect, validate, catalog, install, enable, disable, and
uninstall local packages without executing them.

Signature verification, remote registries, marketplaces, runtime loading, and
generated-skill sandboxing remain deliberately deferred. Those features must
build on this local installation boundary rather than bypass it.

Generated skills will eventually be built and tested in a sandbox before a user
is asked to approve their permissions and installation.
