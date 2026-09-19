# Roadmap

Ally is built in dependency order. A later layer should not become the hidden
implementation of an earlier one.

| Phase | Status | Current implementation |
| --- | --- | --- |
| Foundation | Implemented | local-first architecture, security/data boundaries, CI, ADRs |
| Local conversation | Implemented | provider-neutral chat with local OpenAI-compatible adapter |
| Long-term memory | Implemented V1 | temporal/provenance-aware explicit memory and grounding |
| Personal knowledge | Implemented V1 | versioned plain-text ingestion, retrieval, grounding |
| Tools | Implemented V1 | typed capabilities, risk policy, local audit |
| Skills | Implemented V1 | declarative manifests and dependency validation |
| Reliable agency | Implemented core | persisted tasks, approval pauses, verification, retries |
| Dedicated-hardware validation | Ready to run | reproducible machine/provider validation and runbook |
| Proactivity | Not started | event/attention system |
| Voice | Not started | local ASR/TTS and conversational voice |
| Multi-user households | Not started | identities, shared/private state, permissions |
| Extension ecosystem | Not started | installation, signing, registry/marketplace |
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
- a reproducible local-model validation path.

The repository now contains the deterministic substrate for that target. The
next important engineering evidence comes from running the system against real
local models on the dedicated machine.

## Hardware handoff

Before selecting hardware-specific adapters, default models, context budgets,
or model-driven planning/memory extraction behavior, run the first-machine
procedure in [hardware/apple-silicon-validation.md](hardware/apple-silicon-validation.md).

The initial hardware session should compare real local runtime/model pairs using
the frozen evaluation and validation tooling already in the repository.

## Later dependency order

After hardware/runtime validation:

1. model-planning quality and plan proposal;
2. memory extraction proposals with human inspection;
3. retrieval/embedding upgrades based on measured need;
4. proactive event and attention system;
5. voice;
6. multi-user household boundaries;
7. extension installation/signing/registry;
8. computer control;
9. physical-world integration;
10. distributed Ally.

The first engineering priority remains reliability and compounding usefulness,
not autonomy for its own sake.
