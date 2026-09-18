# Architecture

## Core rule

The LLM is a component inside Ally. Ally is not an application wrapped around a
single LLM.

## Logical layers

```text
Interfaces
    |
Agent Runtime
    |
+---+---------+-----------+
|             |           |
Memory      Models       Tools
|             |           |
Knowledge   Inference   Services
    \          |          /
       Security / Policy
              |
          Local Storage
```

## Dependency direction

Higher-level Ally components depend on Ally-owned interfaces. Vendor SDKs,
model runtimes, databases, and integrations sit behind adapters.

For example:

```text
Ally -> ModelProvider -> MLX / llama.cpp / Ollama / future runtime
```

The same rule will apply to memory persistence, search, tools, secret storage,
and external services.

## Initial runtime

The first implementation is Python 3.12. A TypeScript user interface will be
introduced separately from the core runtime. The first executable interface is
the `ally` CLI.

## Repository strategy

Ally begins as a monorepo. Components should only be split into independent
repositories when independent release or ownership requirements justify it.
