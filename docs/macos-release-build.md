# macOS Release Build Orchestration

Ally's macOS release build is a local orchestration layer over the existing
reviewed helper-build, bundle, signing, notarization, and release-readiness
boundaries.

The orchestrator does not upload artifacts, create Git tags, publish GitHub
releases, select models, fetch updates, or replace an installed application.

## Modes

### Ad-hoc

Ad-hoc mode exists for hosted macOS CI and local release-mechanics testing.

It:

1. requires a clean checkout whose exact `HEAD` matches the supplied full Git
   source revision;
2. builds the Swift release executable;
3. builds the frozen desktop helper;
4. assembles `Ally.app`;
5. ad-hoc signs the helper and outer bundle with no trusted timestamp;
6. verifies the bundle contract;
7. creates `Ally.zip`;
8. extracts and re-verifies that archive; and
9. writes a path-free `release-artifact.json`.

Ad-hoc output is never distributable production evidence.

### Production

Production mode performs the same build flow, but first requires a currently
qualified final release-readiness artifact from #126.

Before any output directory is created it requires:

- exact current Git `HEAD` equals `--source-revision`;
- a clean working tree;
- the final release-readiness report still verifies against the supplied
  validation session and machine-acceptance artifacts;
- a real Developer ID Application identity;
- a pre-existing `notarytool` Keychain profile; and
- a new output destination that does not already exist.

It then:

1. builds the PyInstaller helper with the Developer ID identity so embedded
   native payloads are signed correctly;
2. builds and assembles the application;
3. signs the helper and outer app with hardened runtime and trusted timestamp;
4. submits the app for notarization through the named Keychain profile;
5. staples and validates the ticket;
6. runs Gatekeeper assessment;
7. archives the stapled app;
8. extracts and re-verifies the archive; and
9. writes release metadata bound to the release-readiness SHA-256.

No Apple ID password, API private key, signing certificate, or other secret is
accepted as a command-line argument.

## Output

A successful build creates one output directory outside the repository:

```text
<release-output>/
  Ally.app/
  Ally.zip
  release-artifact.json
```

The metadata contains only release-safe fields:

- Ally version;
- bundle identifier;
- build version;
- bridge protocol version;
- database schema version;
- Git source revision;
- signing mode;
- notarization state;
- archive filename, SHA-256, and size;
- final release-readiness SHA-256 for production builds;
- candidate label and validated-profile ID for production builds.

It contains no credentials, local paths, prompts, model responses, personal
data, or private machine state.

## Ad-hoc CI command

```bash
uv run python scripts/macos_release_pipeline.py build \
  --mode adhoc \
  --source-revision "$(git rev-parse HEAD)" \
  --build-version 1 \
  --output-dir /absolute/path/outside/repository/ally-release \
  --clean
```

## Production command

After the first-machine runbook and final release-readiness verification:

```bash
SOURCE_REVISION="$(git rev-parse HEAD)"

uv run python scripts/macos_release_pipeline.py build \
  --mode production \
  --source-revision "$SOURCE_REVISION" \
  --build-version <monotonic-build-number> \
  --output-dir /absolute/private/release/ally-0.1 \
  --identity "Developer ID Application: <public identity>" \
  --notary-profile <existing-notarytool-keychain-profile> \
  --release-readiness validation/release-readiness.json \
  --validation-session validation/candidate-a/session.json \
  --machine-acceptance validation/machine-acceptance.json
```

The output directory is immutable-by-default in production. The orchestrator
will not delete or replace a prior production output.

## Publication boundary

The resulting ZIP may become the input to a later explicit publication step
only after the real dedicated-machine signing/notarization and replacement
acceptance gates have passed.

Keeping publication separate prevents credentials or GitHub release authority
from being coupled to local runtime/profile evidence or application build code.
