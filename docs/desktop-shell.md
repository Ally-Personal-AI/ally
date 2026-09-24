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
- private-runtime readiness; and
- proactive-service health and attention counts.

This is still an incremental #66 product surface. Validated-profile management,
full attention history/detail, modern bundled notification authorization,
polished empty/error states, and release packaging remain follow-on work.

## Memory and knowledge boundary

Desktop protocol v3 exposes explicit local state-management operations without
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

## Task approval boundary

Desktop protocol v3 retains the v2 task contract and deliberately separates task progression from approval:

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

## Release packaging direction

Development requires an explicit absolute `ALLY_DESKTOP_BRIDGE` path. The native
client does not search `PATH`, and it launches the helper with a minimal
allowlisted environment rather than inheriting arbitrary shell variables. A
release build must not depend on the development environment override.

The intended release shape is one signed/notarized Ally app bundle containing a
pinned local helper/runtime built from the same release revision. The Swift app
will launch that helper by an absolute path inside its own bundle, with private
requests still carried over stdio. The release bundle must preserve Ally's
user-owned application-data locations rather than placing personal state inside
the app bundle.

Before the first desktop release, packaging work must verify:

- app and helper are code-signed together and notarizable;
- the bundled helper uses the locked Python dependency graph and exact Ally
  version expected by the Swift protocol client;
- no release path falls back to an arbitrary executable found on `PATH`;
- closing/reopening the app preserves user-owned state;
- updates replace application code without replacing or migrating user data
  outside Ally's existing migration/recovery boundary; and
- any future updater has its own signed-release and rollback threat model before
  it is allowed to fetch or execute code.

Hardware is still required for final runtime, Keychain, launchd, native
notification, restart, and daily-use acceptance. It is not required to continue
building and testing the desktop presentation architecture.
