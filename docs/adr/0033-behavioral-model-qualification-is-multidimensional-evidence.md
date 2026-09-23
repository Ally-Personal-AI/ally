# ADR 0033: Behavioral model qualification is multidimensional evidence

**Status:** Accepted

## Context

Ally needs evidence about how candidate models behave on legitimate requests,
not only whether they start, follow a smoke instruction, or generate tokens
quickly. A single composite "alignment" or behavior score would hide important
tradeoffs and could encode an opaque preference into model selection.

Viewpoint-symmetry evaluation also needs a neutral construction: paired
framings should be evaluated under the same structural standard without the
evaluator deciding which position is correct.

## Decision

Behavioral qualification records separate evaluation categories for:

- unnecessary refusal;
- instruction following;
- epistemic calibration;
- unsolicited moralizing/evasive assistant framing; and
- paired viewpoint symmetry.

Paired cases use matched prompts and the same objective assertions for both
responses. Initial symmetry checks include requested-section compliance,
minimum substance, refusal behavior, and bounded response-length imbalance.

Validation artifacts fingerprint the exact behavioral suite and preserve its
individual results. Candidate comparison displays behavioral pass counts
separately from core/provider checks and runtime performance. Ally does not
compute a composite behavior score or automatically choose a model.

Behavioral qualification affects model eligibility and routing evidence only.
It cannot grant execution authority or weaken deterministic privacy,
permission, audit, or tool-policy boundaries.

## Consequences

Model behavior can improve independently of Ally identity and user data. Future
evaluators may add stronger semantic symmetry or refusal measurements, but new
dimensions must remain inspectable and versioned rather than being hidden
inside one opaque score.
