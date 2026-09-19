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

## Current scope

Ally can load, inspect, validate, and catalog packages without executing them.
The current CLI accepts an explicit set of available tool names for dependency
validation.

Installation, signatures, remote registries, marketplaces, and generated skill
sandboxing are deliberately deferred. Those features must build on this
manifest boundary rather than bypass it.

Generated skills will eventually be built and tested in a sandbox before a user
is asked to approve their permissions and installation.
