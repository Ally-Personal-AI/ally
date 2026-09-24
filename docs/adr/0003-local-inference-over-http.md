# ADR 0003: First local inference adapter uses OpenAI-compatible HTTP

**Status:** Superseded in part by [ADR 0034](0034-private-intelligence-never-uses-external-inference.md)

## Context

Ally needs a real local inference path before hardware-specific optimization, but the core must not become dependent on llama.cpp, Ollama, MLX, or another runtime.

Several local inference engines can expose an OpenAI-compatible HTTP API.

## Decision

The first production provider adapter targets the OpenAI-compatible chat-completions protocol over HTTP.

The private inference adapter is now loopback-only with no remote override. See ADR 0034. A separately named public-evaluation adapter may contact remote endpoints using only bundled synthetic/public evaluation data.

Hardware-specific adapters may be added later when they provide meaningful capabilities or performance benefits.

## Consequences

Ally can be developed and tested without a real model server by mocking HTTP transport, while real deployments can use multiple local runtimes behind the same provider contract.

This is a transport decision, not a commitment to any external cloud API.
