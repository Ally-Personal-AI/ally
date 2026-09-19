# ADR 0016: Skill installation is local, copied, and non-executing

**Status:** Accepted

## Context

Ally needs an extension lifecycle before it can support a registry or
marketplace. Installing an extension must not be equivalent to executing
untrusted code.

## Decision

The first skill installer accepts only an explicit local directory.

Before installation it:

- parses and validates `skill.toml` as data;
- rejects packages containing symbolic links;
- checks declared required tool names against an explicit available-tool set;
- does not import the declared Python entrypoint.

Validated package files are copied into Ally-owned application data storage
under:

```text
skills/<skill-id>/<version>/
```

Installation metadata is stored alongside the copied package. Newly installed
skills are disabled by default.

Enable and disable are explicit lifecycle operations. Enabling one version of a
skill disables any other enabled version with the same skill ID.

Uninstall removes only the Ally-owned copied package. The original source
directory is never modified.

## Consequences

Ally gains a real extension lifecycle without requiring a remote service or
granting installation-time execution. Future signature verification and remote
registries can sit before this same local installation boundary.
