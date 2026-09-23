"""Deterministic composition for user-owned instruction scopes."""

from __future__ import annotations

from collections.abc import Sequence

from ally.instructions.models import (
    INSTRUCTION_SCOPE_ORDER,
    InstructionContribution,
    UserInstructions,
)


def instruction_contributions(
    profiles: Sequence[UserInstructions],
    *,
    session_instructions: str | None = None,
) -> tuple[InstructionContribution, ...]:
    """Return enabled durable scopes followed by optional ephemeral session input."""

    enabled = sorted(
        (profile for profile in profiles if profile.enabled),
        key=lambda profile: (
            INSTRUCTION_SCOPE_ORDER[profile.scope],
            profile.scope_key,
        ),
    )
    contributions = [
        InstructionContribution(
            scope=profile.scope,
            scope_key=profile.scope_key,
            content=profile.content,
        )
        for profile in enabled
    ]
    session = (session_instructions or "").strip()
    if session:
        contributions.append(
            InstructionContribution(
                scope="session",
                content=session,
            )
        )
    return tuple(contributions)


def render_instruction_contributions(
    contributions: Sequence[InstructionContribution],
) -> str:
    """Render contributions with explicit provenance and stable ordering."""

    blocks: list[str] = []
    for contribution in contributions:
        label = contribution.scope
        if contribution.scope_key:
            label += f":{contribution.scope_key}"
        blocks.append(f"[{label}]\n{contribution.content.strip()}")
    return "\n\n".join(blocks)
