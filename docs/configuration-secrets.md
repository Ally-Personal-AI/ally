# Configuration and Secrets

Ally keeps ordinary configuration and secret material in separate domains.

## Configuration

The current configuration document is versioned JSON and contains only
non-secret values.

Default path:

```text
<OS Ally config directory>/config.json
```

Current schema V1 contains:

- local inference endpoint
- optional non-secret model identifier
- remote-inference privacy defaults

Unknown fields are rejected. There is intentionally no generic free-form
settings dictionary.

Commands:

```bash
uv run ally config path
uv run ally config show
uv run ally config init
uv run ally config validate
```

`config show` returns safe defaults without creating a file when no config
exists. `config init` refuses to overwrite an existing file.

## Secrets

Credentials, tokens, passwords, private keys, and similar values are not Ally
configuration.

Components refer to them with an opaque `SecretRef`:

```json
{
  "name": "service.api-token"
}
```

The actual value is resolved through the `SecretStore` protocol only at the
point a component requires it.

Reference names contain 1–128 lowercase letters, digits, dots, underscores, or
hyphens and must start with a letter or digit.

The repository provides:

- `InMemorySecretStore` for deterministic tests only; and
- `MacOSKeychainSecretStore`, an adapter for the current user's default macOS
  Keychain.

The macOS adapter stores each value as a generic-password item below Ally's
service namespace. A second Keychain item contains only the sorted opaque
reference names, allowing `list` to avoid dumping or scanning unrelated
Keychain records. Values use a versioned encoded envelope before becoming
Keychain data. That envelope is a migration/validation format, not encryption;
Keychain provides the security boundary.

The adapter calls Apple's modern `SecItemCopyMatching`, `SecItemAdd`,
`SecItemUpdate`, and `SecItemDelete` Security-framework APIs directly through a
narrow native boundary. It never launches a secret-bearing subprocess or puts
secret material in process arguments or environment variables. Raw OS status
details are never copied into CLI errors. If Keychain is unavailable, locked,
denied, or contains malformed Ally data, the operation fails closed.

Commands on macOS:

```bash
uv run ally secrets set service.api-token
uv run ally secrets list
uv run ally secrets check service.api-token
uv run ally secrets delete service.api-token
```

`set` accepts no value flag or environment-variable input; it requires a
non-echoing interactive prompt. `list`, `check`, and `delete` print references
and status only. There is deliberately no command that prints a value.

`check` returns status 0 when available, 1 when missing, and 2 when the store
cannot be used safely. `delete` returns 0 when deleted, 1 when already missing,
and 2 on an operational error.

The adapter and CLI are covered by deterministic simulated-Keychain tests on
Linux and macOS CI. macOS CI also exercises a synthetic item through the real
Security framework on its ephemeral runner. Persistence and OS access-prompt
behavior against the dedicated machine's actual login Keychain remain part of
the first-machine acceptance run; see
[Apple Silicon first-machine validation](hardware/apple-silicon-validation.md).

## Deliberate omissions

There is no CLI command for printing or exporting secret values. Ally backup
V1 contains exactly its manifest and SQLite snapshot, so it cannot include
Keychain items, their reference index, or ordinary configuration.

Non-macOS platforms currently fail closed until an operating-system credential
adapter is implemented and validated for that platform.

## Rules for contributors

- Never add raw credential fields to `AllyConfig`.
- Use `SecretRef` in future integration configuration.
- Never log `SecretStr.get_secret_value()`.
- Never place secret material in model context unless a tool explicitly needs
  it and policy permits that use.
- Never add secrets to backup archives, evaluation fixtures, examples, or tests.
- Synthetic secret strings are permitted only in isolated tests and must not be
  copied from real user data.
- Never pass a secret to a subprocess argument, environment variable, log,
  exception message, or model prompt.
