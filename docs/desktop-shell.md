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
- gives each helper request a bounded execution deadline;
- writes stdin and drains bounded stdout concurrently so pipe backpressure
  cannot deadlock the desktop process;
- discards arbitrary helper stderr instead of buffering or surfacing potentially
  private diagnostics;
- terminates and reaps timed-out, cancelled, or oversized helper processes;
- requires every decoded response to carry the exact originating request ID;
- sanitizes failures instead of serializing arbitrary exception messages or
  local paths;
- delegates state and authority decisions to `AllyApplication`; and
- intentionally does **not** expose raw development endpoint/model overrides.

Private desktop chat therefore uses the same active, validated runtime profile
as normal Ally daily inference. Before a real profile exists, the shell can load
local state and health information but private inference remains unavailable.

The Swift client uses one short-lived helper process per request. This is
intentional: it keeps process ownership, failure recovery, and private transport
simple while the product surface is still changing. The lifecycle is fail
bounded: the current default deadline is five minutes, stdout is capped at two
MiB as it is read, blocked stdin writes are covered by the same process deadline,
and task cancellation stops the helper. A persistent bridge process should be
introduced only if measured desktop latency justifies the additional lifecycle
complexity.

## Current surface

The first shell includes:

- bounded startup state from `AllyApplication.bootstrap()`;
- conversation listing, creation, resume, and private chat;
- searchable memory inspection with provenance-preserving correction/retraction;
- searchable knowledge sources with revision/chunk detail and pasted-text ingestion;
- task summary/status inspection;
- task detail with explicit one-step-at-a-time approval and failed-step retry;
- private-runtime readiness and validated-profile catalog/selection;
- explicit portable backup export and read-only archive validation;
- proactive-service health;
- full attention event/delivery-history inspection with explicit handled-state mutation; and
- modern macOS notification authorization/status through `UNUserNotificationCenter`; and
- fail-closed migration from the historical Ally launchd service before signed-app background proactivity.

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

## Portable data boundary

Desktop protocol v15 exposes two explicit portability operations:

- `data.backup` creates a new user-owned `.ally-backup` archive at one exact
  absolute path selected by the user; and
- `data.validate_backup` validates one exact existing archive without changing
  it.

The bridge accepts no overwrite flag, directory, wildcard, restore destination,
or arbitrary read/write command. Creation inherits Ally's existing atomic
no-overwrite behavior. Both operations return only manifest metadata: archive
format/schema, creation timestamp, Ally version, database SHA-256, byte size,
and database schema history. Archive/database bytes never cross the stdio
presentation bridge.

The native System screen obtains paths only from macOS save/open panels and
shows only that metadata. Restore is intentionally absent because replacing the
live database requires the existing offline recovery procedure with Ally
processes stopped.

## Attention, notification, and proactive-service boundary

Desktop protocol v7 keeps the Attention Center and adds a narrow signed-app
delivery handshake without turning the bridge into a general notification API.

Read-only/event-state operations remain:

- `attention.events`;
- `attention.get`;
- `attention.delivery_history`; and
- `attention.mark_handled`.

App-owned proactive delivery uses three additional operations:

- `service.prepare_proactive` acquires Ally's existing `proactive-cycle`
  lease, runs the deterministic scheduler, records a running service-cycle
  entry, and returns only payload-minimized notification candidates;
- `attention.notification_result` accepts only the exact run ID, event ID,
  deterministic delivery key, and success boolean; and
- `service.complete_proactive` accepts only the run ID and computes terminal
  service status from Ally-owned durable counters.

The bridge never accepts a caller-selected notification sink, title, body,
identifier, sound, event payload, delivery-attempt count, or failure count.

Candidates contain only:

- event UUID;
- deterministic `macos.notification` delivery key;
- bounded rendered title/body;
- attention class; and
- event creation timestamp.

The Swift app owns `UNUserNotificationCenter` authorization and delivery.
Before scheduling, it checks current authorization, inspects the app's pending
and delivered notification identifiers, and treats an already-known delivery
key as a successful reconciliation instead of creating a duplicate request.
Apple's local-notification API uses request identifiers for exactly this
kind of request tracking, while Ally's SQLite delivery record remains the
authoritative durable state.

Successful OS delivery still does not mark the underlying event handled.

A prepared run with notification candidates remains `running` until every
native result has been acknowledged and the app calls
`service.complete_proactive`. If the app exits mid-cycle, the next cycle
repairs the abandoned lifecycle record as `interrupted`; delivered
identifiers can then be reconciled without duplicate alerts.

Continuous desktop proactivity is separately opt-in through
`SMAppService.mainApp`. The user can enable/disable launch-at-login behavior
from Ally, and a `requiresApproval` state sends the user to macOS Login Items
settings. Registration does not grant notification permission; notification
authorization remains a separate explicit user choice.

The deprecated Python `NSUserNotificationCenter` adapter remains isolated for
legacy CLI compatibility only. The signed desktop release path does not import
or call it.

### Legacy background-service migration

Protocol v7 also exposes two path-free operations: `service.legacy_status` and
`service.retire_legacy`. The signed app never receives the plist path, prior
Python executable path, or arbitrary launchctl arguments.

Migration is fail closed:

- any configured historical launch agent pauses automatic signed-app proactivity;
- an exact current definition or a recognized historical Ally definition whose
  only allowed difference is its absolute Python executable may be retired;
- modified definitions and symlinks are never removed automatically;
- retirement unloads the exact `ai.ally.proactive-service` label before unlinking
  and re-checks file identity so a racing replacement is not deleted; and
- the new `SMAppService.mainApp` login item cannot be enabled from the UI until
  legacy state is known and no legacy definition remains configured.

This keeps old and new schedulers from silently coexisting even though the
runtime lease would still prevent simultaneous proactive-cycle execution.

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
- `Contents/Resources/release-manifest.json` v2 binds the exact Ally version,
  build number, bridge protocol, supported database schema, helper path,
  SHA-256 of the signed helper bytes, and optional source revision; and
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
in [macos-release-security.md](macos-release-security.md). The implemented
offline forward-only candidate verifier is documented in
[macos-update-trust.md](macos-update-trust.md); it does not fetch or replace
applications.

Hardware is still required for final Developer ID/notarization, runtime,
Keychain, launchd, native notification, restart, app-replacement, and daily-use
acceptance. It is not required to continue building and testing release
architecture.
