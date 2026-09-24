# ADR 0038: Production candidates require functional workflow evidence

**Status:** Accepted

## Context

A model/runtime can pass frozen capability and behavioral evaluations while still
failing when composed with Ally's real conversation, memory, knowledge, tool,
task, planning, backup, or recovery boundaries.

Runtime privacy qualification answers a different question: whether the exact
candidate can operate without prohibited external inference or prompt-bearing
egress. Neither capability nor privacy evidence alone proves integrated Ally
functionality.

Treating disposable workflow checks as console-only diagnostics would leave an
evidence gap: production eligibility could be granted without proving which
capability artifact the functional run actually exercised.

## Decision

A production candidate requires three independently inspectable artifacts tied
to the same exact local-model validation report:

1. capability/behavior validation;
2. runtime privacy qualification; and
3. functional workflow evidence.

Functional workflow evidence is built from the disposable synthetic workflow
run and records only:

- Ally version;
- SHA-256 of the exact source validation artifact;
- source validation success state;
- model/runtime/hardware identity copied from that source;
- workflow check IDs, pass/fail states, durations, and safe exception class
  names; and
- total workflow duration.

It never records model responses, synthetic prompt bodies, temporary workspace
paths, or generated database contents.

The workflow artifact qualifies only when the source capability validation
passed and every functional workflow check passed. Candidate construction
cryptographically verifies both the privacy and workflow artifacts against the
same capability report.

Production eligibility is therefore:

`capability_successful AND privacy_qualified AND workflow_qualified`

No composite score or automatic candidate ranking is introduced.

## Consequences

A candidate with excellent model metrics but failed integrated behavior cannot
be marked production-eligible. A missing or mismatched workflow artifact is
also insufficient.

Workflow failures remain valid diagnostic evidence and should be preserved
rather than hidden. The artifact is immutable and never overwritten.

Future workflow checks may expand as Ally gains capabilities, but changes that
materially alter the evidence contract should be versioned rather than silently
changing prior artifacts.
