# ADR 0024: Executable skills run outside Ally Core

**Status:** Accepted

## Context

Ally skills are installed from user-selected packages. Even when a package has
been validated and explicitly enabled, importing its Python code into the Ally
Core interpreter would give that code access to Core process state and make
failure containment difficult.

The first executable-skill boundary must be useful for local development without
pretending to provide a hardened operating-system sandbox.

## Decision

Executable Python skills must opt in explicitly with:

```toml
entrypoint = "module:function"
execution = "python_subprocess_v1"
```

An entrypoint alone does not grant execution authority.

For `python_subprocess_v1`:

- Ally Core never imports the installed skill module.
- Only an enabled installed version may run.
- Ally launches a separate Python interpreter with `shell=False`.
- The child uses Python isolated mode and disables `site` initialization
  (`-I -S`).
- The child receives a sanitized minimal environment.
- The working directory is the installed skill package.
- The declared module must map to a real file/package below that installed root
  before import is attempted.
- Symbolic links and special files introduced after installation are rejected
  before execution.
- Stdin/stdout use protocol-versioned JSON.
- Input, output streams, and execution time are bounded.
- Child stderr or protocol contamination fails closed.
- The child receives no Ally tool handles, secret store, configuration object,
  database path, memory objects, document handles, or model client.
- V1 executable manifests therefore cannot declare Ally tools or skill config.
- Returned data has no permission authority. Future skill-requested actions must
  enter Ally through the normal tool/policy boundary.

The child interpreter has access only to Python's standard library and the
installed package through the configured import path. Third-party Python
dependencies are not supported in this execution mode.

### Audit

Ally persists payload-free execution metadata:

- installation ID;
- skill ID/version;
- status;
- timestamps/duration;
- process exit code;
- a bounded safe error class.

Inputs, results, stdout, stderr, exception messages, credentials, and arbitrary
skill-defined exception names are not persisted in the execution audit.

### Security limit

This is **process isolation, not a hardened OS sandbox**.

The child normally runs as the same operating-system user as Ally. Code may
still use standard-library APIs to access filesystem or network resources that
the OS user can access if it can discover or construct those locations.

Stronger controls such as OS sandbox profiles, namespaces/containers,
filesystem allowlists, network denial, resource quotas, signing, and trust
policy are separate future layers.

## Consequences

A broken or malicious skill cannot directly mutate Ally Core interpreter state
through an imported module, and the initial data/control boundary is explicit
and testable.

Contributors must not add direct Core imports, tool objects, secrets, or private
state to the V1 worker protocol. New capabilities require an explicit
architecture decision and must preserve Ally's permission model.
