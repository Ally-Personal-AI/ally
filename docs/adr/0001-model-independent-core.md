# ADR 0001: Model-independent core

**Status:** Accepted

## Context

Ally must improve as model technology changes and must run across different hardware ecosystems.

## Decision

Ally Core will depend on Ally-owned model interfaces. Inference engines and vendor SDKs are adapters. No model runtime may become the architectural center of the application.

## Consequences

This introduces modest adapter overhead but makes models and runtimes replaceable without changing Ally's identity, memory, or higher-level behavior.
