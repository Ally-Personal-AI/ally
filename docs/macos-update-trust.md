# macOS Update Candidate Trust

Ally does not currently have an automatic updater.

Before an updater is allowed to download or replace executable code, the
repository provides an **offline candidate-verification boundary**. Its job is
to decide whether one already-staged `Ally.app` may be considered a valid
forward update of another already-installed `Ally.app`.

It performs no network request and never replaces either application.

## Signed release metadata

Release manifest schema v2 binds:

- stable bundle identifier `ai.ally.personal`;
- exact Ally package version;
- monotonically increasing positive build number;
- desktop bridge protocol version;
- supported Ally database schema version;
- fixed embedded-helper path;
- SHA-256 of the final signed helper bytes; and
- optional full 40-character lowercase Git source revision.

A candidate accepted for release/update use must carry a full source revision.

The bundle's `CFBundleVersion` and `CFBundleShortVersionString` are checked
against the signed release manifest so display/build metadata cannot silently
diverge from the manifest.

## Structural comparison

For deterministic development/CI checks:

```bash
uv run python scripts/macos_update_trust.py compare \
  --current /path/to/Current-Ally.app \
  --candidate /path/to/Candidate-Ally.app
```

This validates bundle/manifest/helper structure and applies forward-only policy,
but it is **not** production signature authentication.

The candidate is rejected when:

- either bundle identity is not `ai.ally.personal`;
- the candidate build is the same as or older than the installed build;
- the semantic app version moves backward;
- the bridge protocol moves backward;
- supported database schema moves backward;
- either release lacks release-grade source provenance; or
- the current and candidate bundles are the same/nested path.

If the candidate raises the supported database schema version, successful output
sets `requires_pre_migration_backup=true`. A future installer must create and
validate Ally's existing backup artifact before allowing that candidate to
perform a potentially rollback-breaking migration.

## Production macOS trust verification

For a real signed/notarized candidate:

```bash
uv run python scripts/macos_update_trust.py verify-update \
  --current /Applications/Ally.app \
  --candidate /private/staging/Ally.app \
  --team-id <APPLE-DEVELOPER-TEAM-ID>
```

In addition to the structural/forward checks, **both** applications must pass:

- `codesign --verify --deep --strict`;
- exact bundle identifier;
- exact expected Developer ID TeamIdentifier;
- hardened-runtime flag;
- trusted signing timestamp;
- `stapler validate`; and
- Gatekeeper `spctl --assess --type execute`.

The verifier invokes fixed absolute Apple tool paths and does not use a shell.
Raw subprocess output and local application paths are not returned in the
accepted JSON result.

## Pre-install preparation

A verified forward candidate can be prepared without replacing application code:

```bash
uv run python scripts/macos_update_prepare.py \
  --current /Applications/Ally.app \
  --candidate /private/staging/Ally.app \
  --team-id <APPLE-DEVELOPER-TEAM-ID>
```

If the candidate raises the supported database schema, preparation fails closed
unless a fresh backup destination is supplied:

```bash
uv run python scripts/macos_update_prepare.py \
  --current /Applications/Ally.app \
  --candidate /private/staging/Ally.app \
  --team-id <APPLE-DEVELOPER-TEAM-ID> \
  --backup-output /absolute/private/path/before-update.ally-backup
```

Preparation always authenticates the installed and candidate applications first.
When a backup is requested, Ally creates it through the existing atomic
backup boundary, re-opens it through the normal validation path, verifies that
its schema tail matches the installed release contract, and SHA-256 binds both
the archive and contained database into a path-free preparation record.

The preparation boundary does not fetch an update, replace `Ally.app`, or run
the candidate's database migrations. A backup may also be requested for a
non-schema-raising update as an additional operator safety measure.

## Deliberate non-capabilities

This boundary does not:

- fetch release metadata;
- choose a release channel;
- download an app;
- accept delta/binary patches;
- replace the installed app;
- mutate Ally user data;
- migrate or downgrade the database;
- provide a rollback override; or
- expose update authority to model output, tools, skills, or the desktop helper.

Those capabilities should be added only after the verification and recovery
contracts are accepted on the dedicated Mac.

## Hosted CI

Hosted macOS CI builds two local release bundles with increasing build numbers
and confirms structural comparison accepts the newer candidate.

Both bundles are only ad-hoc signed in CI. The production `verify-update`
operation is therefore expected to reject them. That negative test ensures an
ad-hoc signature cannot accidentally satisfy the Developer ID/notarization
boundary.

## Dedicated-machine acceptance

Before an updater or automated replacement is enabled:

1. build/sign/notarize two synthetic release candidates with the real Developer
   ID identity and unique increasing build numbers;
2. install the older release and confirm Gatekeeper launch;
3. run `verify-update` against the newer staged release using the real Team ID;
4. confirm the path-free accepted result and source revision;
5. test an equal-build and older-build candidate and confirm rejection;
6. test a candidate signed by another identity and confirm rejection;
7. test an unstapled/unnotarized candidate and confirm rejection;
8. for a synthetic schema-bump candidate, confirm
   `requires_pre_migration_backup=true`; and
9. only then exercise manual app replacement while confirming Ally user-owned
   state remains outside the application bundle.

Automatic fetching/replacement remains a separate future decision.
