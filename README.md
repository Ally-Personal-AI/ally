# Ally

**Ally is a local-first, user-owned personal AI platform.**

Ally is being built toward a private, persistent artificial intelligence that can learn a user's world, remember accurately over long periods, use interchangeable local models, work with tools, and eventually act within explicit user-defined boundaries.

> Models are replaceable. Memory persists. Tools are extensible. Policies are programmable. Data belongs to the user. The assistant evolves.

## Status

Ally is in very early development. It is not yet suitable for consequential automation or storing irreplaceable sensitive information.

The first target, **Ally 0.1**, is a completely local, model-independent personal AI with persistent conversations, inspectable long-term memory, personal document knowledge, optional internet research, and strong local-data boundaries.

## Architecture

The foundational rule is simple:

**The LLM is a component inside Ally. Ally is not an application wrapped around one LLM.**

Inference engines such as MLX, llama.cpp, Ollama, CUDA-backed runtimes, and future systems will sit behind Ally-owned provider interfaces. Replacing a model must not replace Ally's memory, identity, or higher-level behavior.

See:

- [Vision](docs/vision.md)
- [Principles](docs/principles.md)
- [Architecture](docs/architecture.md)
- [Security model](docs/security-model.md)
- [Memory model](docs/memory-model.md)
- [Roadmap](docs/roadmap.md)
- [Architecture decisions](docs/adr/README.md)

## Development

Ally currently targets Python 3.12 and uses [uv](https://docs.astral.sh/uv/) for environment and dependency management.

```bash
git clone https://github.com/Ally-Personal-AI/ally.git
cd ally
uv sync --extra dev
uv run ally doctor
uv run pytest
```

Quality checks:

```bash
uv run ruff check .
uv run pyright
uv run pytest --cov=ally
```

## Personal data boundary

Personal runtime data, memory databases, secrets, downloaded model weights, generated indexes, and private logs are deliberately kept outside the repository.

Development fixtures must use synthetic or appropriately licensed public data.

## Contributing

Ally is being designed as an open ecosystem. The project is still foundational, so architectural consistency matters more than adding features quickly. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

## License

Apache License 2.0. See [LICENSE](LICENSE).
