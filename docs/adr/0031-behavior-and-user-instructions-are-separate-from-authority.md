# ADR 0031: Behavior and user instructions are separate from authority

**Status:** Accepted

## Context

Ally is intended to be a highly capable personal AI whose models are
replaceable. Users need durable control over response style and working
instructions without turning model prompts into the security boundary.

The project also needs a clear behavioral objective for model qualification:
minimize unnecessary refusal and viewpoint asymmetry while preserving factual
calibration and honest capability limits.

## Decision

Ally will maintain three separate concepts:

1. a fixed Ally behavioral contract owned by the project;
2. private user-owned instructions that customize behavior and work style; and
3. deterministic capability/privacy policy that remains authoritative over
   external actions and protected data.

User instructions are personal state and therefore live in the user-owned
database rather than ordinary non-secret configuration.

The initial instruction scope is one global profile. Prompt composition may use
that profile, but neither the behavioral contract nor user instructions can
grant tool permissions, bypass audit, change privacy boundaries, or modify
their own authority.

## Consequences

Users can deeply customize Ally without coupling their preferences to a model
vendor or weakening execution controls. Model behavior can be evaluated and
changed independently of persistent instructions. Additional instruction scopes
can be added later behind the same explicit composition boundary.
