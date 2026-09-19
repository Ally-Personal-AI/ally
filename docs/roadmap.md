# Roadmap

Ally is built in dependency order. A later layer should not become the hidden
implementation of an earlier one.

| Phase | Status | Current implementation |
| --- | --- | --- |
| Foundation | Implemented | local-first architecture, tested dependency boundaries, contributor map, locked dependencies, Linux quality CI + macOS portability smoke, coverage regression gate, automated dependency maintenance, security/data boundaries, ADRs |
| Data portability | Implemented V1 | versioned integrity-checked SQLite backup/restore archives |
| Configuration / secrets | Implemented boundary | strict non-secret config, secret references, backend abstraction |
| Local conversation | Implemented | provider-neutral chat with local OpenAI-compatible adapter |
| Long-term memory | Implemented V1 | temporal/provenance-aware explicit memory and grounding |
| Personal knowledge | Implemented V1 | versioned plain-text ingestion, retrieval, grounding |
| Tools | Implemented V1 | typed capabilities, risk policy, local audit |
| Skills | Implemented V1 | declarative manifests, safe install lifecycle, explicit process-isolated Python execution |
| Reliable agency | Implemented core | persisted tasks, approval pauses, verification, retries |
| Model plan proposals | Implemented boundary | strict TaskPlan proposals; no persistence or execution authority |
| Model memory proposals | Implemented boundary | reviewable extraction bundles; explicit selected acceptance only |
| Dedicated-hardware validation | Ready to run | reproducible machine/provider validation and runbook |
| Proactivity | Implemented substrate | persisted events, deterministic attention, scheduling, delivery, restart-safe sources, lease-protected cycle, portable lifecycle, structured read-only readiness |
| Voice | Not started | local ASR/TTS and conversational voice |
| Multi-user households | Not started | identities, shared/private state, permissions |
| Extension ecosystem | Implemented local foundation | local lifecycle + isolated execution; signing, mediated tool requests, and registry deferred |
| Computer control | Not started | GUI perception/action behind tool policy |
| Physical-world integration | Not started | devices, sensors, automation |
| Distributed Ally | Not started | coordinated compute/storage nodes |

## Ally 0.1

The first meaningful release target is a completely local, model-independent
personal AI with:

- persistent conversations;
- inspectable long-term memory;
- personal document knowledge;
- explicit privacy boundaries;
- permissioned tool execution;
- restart-safe task execution;
- behavioral evaluations;
- user-owned portable backups;
- a reproducible local-model validation path.

The repository now contains the deterministic substrate for that target. The
next important engineering evidence comes from running the system against real
local models on the dedicated machine.

## Pre-hardware hardening

The repository pins the complete Python dependency graph in `uv.lock`. CI
installs only that locked graph on Linux and macOS, enforces a project-wide
coverage regression floor, and groups weekly Python and GitHub Actions updates
for review.

These controls keep the first-machine evidence comparable over time: a model or
runtime comparison should not silently change because unrelated dependencies
floated between runs.

## Hardware handoff

Before selecting hardware-specific adapters, default models, context budgets,
or enabling any automatic model-driven planning or memory behavior, run the
first-machine procedure in [hardware/apple-silicon-validation.md](hardware/apple-silicon-validation.md).

The safe proposal boundaries for planning and memory formation are already in
place; the hardware session now measures whether candidate local models are good
enough to use those boundaries reliably.

The initial hardware session should compare real local runtime/model pairs using
the frozen evaluation and validation tooling already in the repository.

## Later dependency order

After hardware/runtime validation:

1. choose the first supported runtime/model profile from measured results;
2. decide whether direct MLX or other hardware-specific adapters are justified;
3. calibrate planning and memory proposal quality thresholds;
4. upgrade retrieval/embeddings only where measured need justifies it;
5. add real calendar/email/filesystem/weather source adapters, thin OS service wrappers, and platform notification sinks on the persisted proactivity substrate;
6. add voice;
7. add multi-user household boundaries;
8. add skill signing and remote registry on top of the local installation boundary;
9. add computer control;
10. add physical-world integration;
11. add distributed Ally.

The first engineering priority remains reliability and compounding usefulness,
not autonomy for its own sake.
