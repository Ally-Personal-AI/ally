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


def run_propose_memories(
    *,
    endpoint: str,
    model: str,
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
        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
        ) as provider:
            bundle = ModelMemoryProposer(provider).propose(
                text=text,
                source=source,
                privacy=privacy,
            )
    except (ModelProviderError, MemoryProposalError, ValueError) as exc:
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
