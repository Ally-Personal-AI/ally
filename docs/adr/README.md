# Architecture Decision Records

Significant, hard-to-reverse architectural choices are recorded here.

Each ADR includes context, a decision, consequences, and status. Changes should
supersede previous ADRs rather than silently rewriting project history.

## Decision log

1. [Model-independent core](0001-model-independent-core.md)
2. [Personal data stays outside the repository](0002-personal-data-outside-repository.md)
3. [Local inference over HTTP](0003-local-inference-over-http.md)
4. [SQLite local persistence](0004-sqlite-local-persistence.md)
5. [Temporal, provenance-aware memory](0005-temporal-provenance-memory.md)
6. [Retrieved context is untrusted data](0006-retrieved-context-is-untrusted-data.md)
7. [Versioned personal knowledge](0007-versioned-personal-knowledge.md)
8. [Permissioned tool execution](0008-permissioned-tool-execution.md)
9. [Declarative skill packages](0009-declarative-skill-packages.md)
10. [Persisted task state](0010-persisted-task-state.md)
11. [Model plan proposals are data](0011-model-plan-proposals-are-data.md)
12. [Memory extraction is reviewable](0012-memory-extraction-is-reviewable.md)
13. [Events before proactivity](0013-events-before-proactivity.md)
14. [Versioned portable backups](0014-versioned-portable-backups.md)
15. [Configuration never contains secrets](0015-config-never-contains-secrets.md)
16. [Local skill installation is non-executing](0016-local-skill-installation-is-nonexecuting.md)
17. [Schedules produce idempotent events](0017-schedules-produce-idempotent-events.md)
18. [Attention delivery is separate from handling](0018-attention-delivery-is-separate-from-handling.md)
19. [The proactive service cycle is bounded](0019-proactive-service-cycle-is-bounded.md)
20. [Event sources use cursors and dedupe](0020-event-sources-use-cursors-and-dedupe.md)
21. [Service coordination leases are ephemeral runtime state](0021-service-leases-are-ephemeral.md)
22. [Service lifecycle history is portable and payload-free](0022-service-lifecycle-is-portable-and-payload-free.md)

## Adding an ADR

Use the next four-digit sequence number and a short kebab-case filename. Record
the decision before or with the implementation that depends on it. If a later
decision replaces an earlier one, mark the earlier ADR superseded and link both
directions rather than deleting history.
