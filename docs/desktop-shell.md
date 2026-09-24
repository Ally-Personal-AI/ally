# Native macOS Desktop Shell

The first Ally desktop surface is a thin native SwiftUI presentation layer over
the existing UI-neutral `AllyApplication` boundary.

Its purpose is to make Ally usable without moving conversation, memory,
knowledge, task, privacy, or model-selection semantics into the UI.

## Architecture

```text
SwiftUI app
   |
   | bounded JSON over local stdin/stdout
   v
ally-desktop-bridge
   |
   v
AllyApplication
   |
   v
existing composition / runtime / domain boundaries
```

The bridge is a presentation adapter, not a new service layer. It:

- opens no TCP or Unix-domain listener;
- sends private request payloads over stdin rather than process arguments;
- returns responses over stdout;
- applies a one-MiB request bound and stable protocol version;
- sanitizes failures instead of serializing arbitrary exception messages or
  local paths;
- delegates state and authority decisions to `AllyApplication`; and
- intentionally does **not** expose raw development endpoint/model overrides.

Private desktop chat therefore uses the same active, validated runtime profile
as normal Ally daily inference. Before a real profile exists, the shell can load
local state and health information but private inference remains unavailable.

The initial Swift client uses one short-lived helper process per request. This is
intentional: it keeps process ownership, failure recovery, and private transport
simple while the product surface is still changing. A persistent bridge process
should be introduced only if measured desktop latency justifies the additional
lifecycle complexity.

## Current surface

The first shell includes:

- bounded startup state from `AllyApplication.bootstrap()`;
- conversation listing, creation, resume, and private chat;
- searchable memory inspection with provenance-preserving correction/retraction;
- searchable knowledge sources with revision/chunk detail and pasted-text ingestion;
- task summary/status inspection;
- task detail with explicit one-step-at-a-time approval and failed-step retry;
- private-runtime readiness and validated-profile catalog/selection;
- proactive-service health;
- full attention event/delivery-history inspection with explicit handled-state mutation; and
- modern macOS notification authorization status/request through `UNUserNotificationCenter`.

This is still an incremental #66 product surface. Polished empty/error states,
real Developer ID/notarization acceptance, and dedicated-machine release
validation remain follow-on work.

## Validated runtime selection boundary

Desktop protocol v4 exposes only the installed validated-profile catalog and
exact profile selection/deselection:

- the desktop cannot install a profile or supply evidence-file paths;
- it cannot supply a raw endpoint, model name, or runtime coordinate;
- the application catalog returns path-free qualification metadata and evidence
  digests for inspection;
- selecting requires the exact deterministic ID of an already-installed
  validated profile;
- active selection remains hash-bound to the exact installed profile bytes; and
- catalog browsing now also rejects installed filenames that do not match the
  profile's self-derived identity.

The default composition gives the application facade and private-inference
resolver the same `RuntimeProfileCatalog` instance. A profile selected in the
native UI therefore becomes the same active profile used by daily private chat.
If the selection or installed profile is missing, changed, or invalid, inference
fails closed instead of silently falling back.

## Memory and knowledge boundary

Desktop protocol v4 retains the v3 memory/knowledge operations and exposes explicit local state-management operations without
granting broader filesystem or model authority:

- memory correction calls `AllyApplication.supersede_memory()`, preserving the
  original record and creating a linked replacement rather than overwriting
  history;
- memory retraction preserves the record and provenance while removing it from
  active retrieval;
- inactive memories cannot be corrected through the application boundary;
- knowledge detail exposes stored source/revision/chunk provenance;
- knowledge search uses Ally's existing local lexical retriever; and
- desktop ingestion accepts bounded pasted UTF-8 text only. The bridge does not
  accept a filesystem path, open arbitrary files, or invoke a model during
  ingestion.

The native UI makes those semantics visible before mutation and explains that
correction/retraction preserve local history.

## Attention and notification boundary

Desktop protocol v5 adds a dedicated local Attention Center without turning the
presentation layer into a notification-delivery engine:

- `attention.events` lists user-facing `mention_later`, `notify`, and
  `interrupt` events, including handled history when requested;
- `attention.get` returns one event plus every durable sink-delivery record;
- `attention.delivery_history` exposes bounded delivery history;
- `attention.mark_handled` changes only the event's local handled state;
- successful notification delivery still does not imply that the user handled
  the underlying event; and
- the bridge exposes no desktop command for forcing delivery, choosing a sink,
  or changing attention classification.

The Swift app also uses Apple's modern `UNUserNotificationCenter` API to read
notification authorization state and to request alert/sound permission only
after an explicit user action. That permission client has no access to Ally's
event store, delivery store, or bridge.

The existing background Python/launchd delivery adapter remains isolated behind
the durable `AttentionSink` contract. Replacing its deprecated
`NSUserNotificationCenter` backend with app-bundle-owned modern delivery is a
separate packaging/identity transition and must not be claimed complete until
the signed application bundle and dedicated-machine behavior are validated.

## Task approval boundary

Desktop protocol v4 retains the exact-step task contract and deliberately separates task progression from approval:

- `task.run` accepts only a task ID and cannot carry approvals;
- `task.approve_step` accepts exactly one task ID plus one step ID;
- the application facade verifies that the selected step currently has
  `approval_required` status before forwarding that one ID to `TaskRunner`;
- stale, premature, or bulk approvals fail closed; and
- `task.retry_step` only resets an explicitly selected failed step.

The native UI displays the tool name, exact arguments, durable step ID, prior
output/error state, and a confirmation dialog before approval. After one
approval, Ally may execute later steps that policy permits without approval, but
must pause again at the next approval-required step.

## Development

Install the locked Ally environment first:

```bash
uv sync --locked --extra dev
```

Point the native development shell at the installed helper with an absolute
path, then run the Swift package:

```bash
export ALLY_DESKTOP_BRIDGE="$(pwd)/.venv/bin/ally-desktop-bridge"
swift run --package-path desktop/macos AllyDesktop
```

The helper can also be exercised directly without a GUI:

```bash
printf '%s\n' \
  '{"id":"1","method":"bridge.info","params":{}}' \
  | uv run ally-desktop-bridge --once
```

Do not put prompts, messages, document contents, memory contents, credentials,
or other private Ally state into helper command-line arguments or environment
variables.

## Release packaging foundation

Release-mode helper resolution now has a fail-closed bundle contract:

- the stable bundle identifier is `ai.ally.personal`;
- debug builds may use the explicit absolute `ALLY_DESKTOP_BRIDGE` override;
- release builds ignore that override and never search `PATH`;
- the only release helper path is
  `Contents/Helpers/ally-desktop-bridge`;
- `Contents/Resources/release-manifest.json` binds the exact Ally version,
  bridge protocol, helper path, and SHA-256 of the signed helper bytes; and
- Swift verifies the manifest and helper digest before launch.

The deterministic assembler is `scripts/macos_app_bundle.py`. It builds the
minimal app layout, emits `Info.plist`, creates the release manifest, preserves
the user-data boundary, and can verify the result independently.

The signing/notarization boundary is
`scripts/macos_release_signing.py`. The intended production order is helper
signing, post-sign helper-hash refresh, outer app signing, signature
verification, notarization through an existing `notarytool` Keychain profile,
ticket stapling, and Gatekeeper assessment.

Hosted macOS CI builds the actual Swift release executable and a self-contained
one-file `ally-desktop-bridge`, executes the frozen helper's `bridge.info` and
`bootstrap` operations outside the repository checkout, assembles the real
`Ally.app`, and ad-hoc signs/verifies the nested helper and outer application.

The helper build currently pins PyInstaller 6.22.3 and
`pyinstaller-hooks-contrib` 2026.7 in the release CI command. The resulting
helper does not depend on the repository checkout, a developer virtual
environment, `PATH`, Homebrew, or an externally installed Python runtime.

For a real Developer ID release, the Developer ID Application identity must also
be supplied to the PyInstaller helper-build step so the binary payload embedded
inside the one-file helper receives the correct signing identity before the
outer app is signed.

The full signing, notarization, updater, and rollback threat model is documented
in [macos-release-security.md](macos-release-security.md).

Hardware is still required for final Developer ID/notarization, runtime,
Keychain, launchd, native notification, restart, app-replacement, and daily-use
acceptance. It is not required to continue building and testing release
architecture.
