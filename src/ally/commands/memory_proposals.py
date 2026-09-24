"""Human-facing memory proposal presentation adapter."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ally.application import MemoryProposalRequest
from ally.composition import build_default_application
from ally.memory import (
    MemoryPrivacy,
    MemoryProposalBundle,
    MemoryProposalError,
    MemorySourceType,
)
from ally.models.errors import ModelProviderError
from ally.runtime_profiles import InferenceTargetError


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
    try:
        bundle = build_default_application().propose_memories(
            MemoryProposalRequest(
                text=text,
                source_type=source_type,
                source_id=source_id,
                source_uri=source_uri,
                privacy=privacy,
                development_endpoint=development_endpoint,
                development_model=development_model,
            )
        )
    except InferenceTargetError as exc:
        print(f"Inference target error: {exc}")
        return 2
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
        created = build_default_application().accept_memory_proposals(
            bundle,
            indices=indices,
        )
    except ValueError as exc:
        print(f"Memory proposal error: {exc}")
        return 2

    for record in created:
        print(record.id)
    return 0
