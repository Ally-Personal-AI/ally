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

Future components refer to them with an opaque `SecretRef`:

```json
{
  "name": "service.api-token"
}
```

The actual value is resolved through the `SecretStore` protocol only at the
point a component requires it.

The repository currently provides `InMemorySecretStore` for deterministic
tests and development. It is ephemeral and is not a production credential
backend.

A platform secure-store implementation (for example macOS Keychain) will
implement the same interface after validation on target hardware.

## Deliberate omissions

There is currently no CLI command for entering or printing secret values.
There is also no secret export in Ally backup V1.

These omissions are intentional. A secure credential path should be added only
when the platform backend can be validated end to end.

## Rules for contributors

- Never add raw credential fields to `AllyConfig`.
- Use `SecretRef` in future integration configuration.
- Never log `SecretStr.get_secret_value()`.
- Never place secret material in model context unless a tool explicitly needs
  it and policy permits that use.
- Never add secrets to backup archives, evaluation fixtures, examples, or tests.
- Synthetic secret strings are permitted only in isolated tests and must not be
  copied from real user data.
