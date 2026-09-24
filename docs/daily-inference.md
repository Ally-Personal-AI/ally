# Daily Inference Target Resolution

Ally separates validated daily-use inference from model development and
candidate testing.

## Daily use

Once a validated runtime profile is installed and selected:

```bash
ally profiles select <profile-id>
ally chat
ally plan propose --goal "Inspect the local runtime"
ally memory propose "I prefer tea over coffee."
```

These commands resolve the active validated profile automatically.

The resolved target contains the selected profile ID, loopback endpoint, model,
runtime name/version, and provenance indicating that it came from validated
selection.

## Development override

Before a candidate is validated—or when testing a local candidate explicitly—
use both development fields:

```bash
ally chat \
  --development-endpoint http://127.0.0.1:11434/v1 \
  --development-model <model-id>
```

The same development options are available on `plan propose` and
`memory propose`.

Both values are required together. Remote endpoints are rejected. Development
targets do not carry a validated profile ID or runtime qualification claim.

## Fail-closed behavior

Daily commands do not silently fall back to default model coordinates.

Inference fails before any request when:

- no active validated profile is selected;
- the active selection is malformed;
- the installed profile is missing;
- the selected profile bytes changed after selection; or
- the profile itself is invalid.

For chat, target resolution also occurs before conversation creation/resume and
private context loading.

Provider/runtime connection failures are reported separately from inference
target/selection failures.

## Boundaries

Candidate validation commands deliberately continue accepting raw candidate
endpoint/model information because they create the evidence required to become
a validated profile.

Remote public/synthetic evaluation remains a separate provider and does not
create a path for private Ally state.
