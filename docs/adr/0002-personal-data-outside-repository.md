# ADR 0002: Personal data lives outside the repository

**Status:** Accepted

## Context

Ally will eventually contain highly sensitive personal information. Development repositories are designed for source code, collaboration, and publication.

## Decision

Personal runtime data, memories, credentials, model weights, indexes, and logs containing private information are excluded from the repository and stored in OS-appropriate local application directories or explicitly configured external storage.

## Consequences

Development fixtures must use synthetic data. Local runtime paths are explicit and testable. Accidental commits are reduced but must still be guarded against with tooling and review.
