# ADR 0008: All tool execution passes through policy and audit

**Status:** Accepted

## Context

Ally will eventually use tools that can read private information, modify files,
communicate externally, spend money, or affect physical systems. A model prompt
is not an adequate authorization boundary.

## Decision

Tools declare a stable name, description, and risk class. Tool invocation occurs
only through an Ally-owned executor that consults deterministic policy before
calling the tool and writes a local audit record for every attempt.

The initial risk classes are:

- read-only
- reversible
- external consequence
- high consequence

The default policy allows read-only tools, requires explicit approval for
reversible and externally consequential tools, and denies high-consequence tools.

Unknown tools fail closed.

## Consequences

Models, skills, and future agents cannot directly execute tools without passing
through the same authorization path. More sophisticated user-defined policy can
replace the initial policy later without changing tool implementations.
