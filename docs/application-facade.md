# Ally Application Facade

`ally.application` is the typed, UI-neutral daily-use interface shared by
presentation layers.

It exists so the CLI, future desktop app, and future local clients can use the
same privacy, persistence, grounding, and model-selection behavior.

## Current V1 core

The first application slice exposes:

- runtime inference readiness and resolved target provenance;
- conversation creation/listing/detail;
- private chat turns with persistent history;
- scoped global/project/conversation/task/session user instructions;
- bounded memory + personal-knowledge grounding;
- explicit memory create/search/list/get/supersede/retract;
- reviewable model-generated memory proposals;
- explicit selected proposal acceptance only;
- knowledge source listing/detail/search;
- UTF-8 file ingestion; and
- direct in-memory text ingestion for non-CLI interfaces;
- persisted task create/list/detail/run/retry through the existing deterministic
  tool policy and exact-step approval boundary;
- pending attention and durable delivery-history reads; and
- payload-free service health and lifecycle-history reads.

All request/result models are Pydantic models or existing immutable Ally domain
models and are suitable for local UI serialization.

## Desktop bootstrap contract

The intended first call for the minimal native desktop shell is:

```python
snapshot = build_default_application().bootstrap()
```

`AllyBootstrapSnapshot` is a bounded, immutable, serialization-friendly
dashboard/startup view containing:

- private inference readiness and active validated-runtime provenance when ready;
- recent conversations;
- recent tasks, including `waiting_approval`;
- pending attention;
- recent attention delivery history;
- recent proactive service lifecycle history; and
- read-only service health.

Collection sizes are bounded by `BootstrapLimits` (20/20/20/20/10 by default,
with each collection capped at 100).

Bootstrap is deliberately best-effort. A missing active runtime is represented
inside `runtime` and does not prevent local state from loading. Operational
services omitted by a custom/test composition return explicit `unavailable`
sections. Ordinary subsection read failures return a stable `read_failed`
code without serializing exception messages, file paths, or private diagnostic
details.

The bootstrap call has no external side effects: it does not run tasks, approve
steps, deliver notifications, execute a service cycle, invoke a model, or mutate
attention state.

## Private chat path

The shared chat flow is:

```text
presentation adapter
      |
      v
AllyApplication.send_message
      |
      +--> resolve_inference_target
      |       |
      |       +--> active validated profile (normal)
      |       +--> explicit loopback dev override
      |
      +--> conversation store
      +--> scoped instructions
      +--> memory + knowledge context
      +--> ModelProvider
      +--> PersistentConversationRuntime
      |
      v
durable user + assistant exchange
```

Inference target resolution happens before conversation/private-context access.
A missing, invalid, or tampered active profile therefore fails before a new chat
record is created.

## Composition

`ally.application` depends only on Ally-owned protocols and reusable runtime
logic.

`ally.composition.build_default_application()` supplies the concrete local
adapters:

- SQLite conversation/memory/knowledge/instruction stores;
- default user-owned data path;
- current loopback OpenAI-compatible provider; and
- validated inference target resolver.

The concrete composition edge is replaceable without changing the public
application contract.

## Authority

The facade does not grant additional authority.

Memory proposals remain proposals until explicitly selected. Retrieved context
remains untrusted reference data. Model inference remains loopback-only.
Existing tool/task permission rules remain authoritative. The facade's
`run_task()` delegates to the existing `TaskRunner`: reversible and
externally consequential steps still pause until their exact step IDs are
explicitly approved, while high-consequence tools remain denied by policy.

Notification delivery and proactive service-cycle execution are intentionally
not application-facade operations yet. They remain explicit presentation/runtime
actions until their future UI authorization flow is modeled separately.

## Presentation rule

Do not add terminal formatting, prompts, `argparse`, GUI toolkit objects, or
web-framework response objects to `ally.application`.

Presentation layers transform typed application results into their own UI.
