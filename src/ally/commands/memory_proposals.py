"""Human-facing memory proposal and acceptance commands."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ally.commands._storage import build_memory_store
from ally.memory import (
    MemoryPrivacy,
    MemoryProposalBundle,
    MemoryProposalError,
    MemorySource,
    MemorySourceType,
    ModelMemoryProposer,
)
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider
from ally.runtime_profiles import InferenceTargetError, resolve_inference_target


def run_propose_memories(
    *,
    development_endpoint: str | None,
    development_model: str | None,
    text: str,
    source_type: MemorySourceType,
    source_id: str | None,
    source_uri: str | None,
    privacy: MemoryPrivacy,
    output: str | None,
) -> int:
    source = MemorySource(
        type=source_type,
        id=source_id,
        uri=source_uri,
    )

    try:
        target = resolve_inference_target(
            development_endpoint=development_endpoint,
            development_model=development_model,
        )
    except InferenceTargetError as exc:
        print(f"Inference target error: {exc}")
        return 2

    try:
        with OpenAICompatibleProvider(
            base_url=target.endpoint,
            model=target.model,
        ) as provider:
            bundle = ModelMemoryProposer(provider).propose(
                text=text,
                source=source,
                privacy=privacy,
            )
    except ModelProviderError as exc:
        print(f"Memory provider error: {exc}")
        return 2
    except (MemoryProposalError, ValueError) as exc:
        print(f"Memory proposal error: {exc}")
        return 2

    rendered = json.dumps(
        bundle.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
    )

    if output is None:
        print(rendered)
    else:
        destination = Path(output).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
        print(destination)

    return 0


def run_accept_memory_proposals(
    *,
    proposal_path: str,
    indices: tuple[int, ...],
) -> int:
    if not indices:
        print("At least one --index is required.")
        return 2
    if len(indices) != len(set(indices)):
        print("Proposal indices must be unique.")
        return 2

    path = Path(proposal_path).expanduser().resolve()
    try:
        raw = path.read_text(encoding="utf-8")
        bundle = MemoryProposalBundle.model_validate_json(raw)
    except OSError as exc:
        print(f"Memory proposal error: {exc}")
        return 2
    except ValidationError as exc:
        print(f"Memory proposal error: {exc}")
        return 2

    try:
        selected = tuple(bundle.accepted_memory(index) for index in indices)
    except ValueError as exc:
        print(f"Memory proposal error: {exc}")
        return 2

    store = build_memory_store()
    created = tuple(store.create(memory) for memory in selected)

    for record in created:
        print(record.id)
    return 0
