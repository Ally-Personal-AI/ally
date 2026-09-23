"""CLI operations for private scoped user instruction profiles."""

from __future__ import annotations

from ally.commands._storage import build_user_instructions_store
from ally.instructions import (
    InstructionContext,
    InstructionScope,
    instruction_contributions,
    render_instruction_contributions,
)


def _scope_label(scope: InstructionScope, scope_key: str | None) -> str:
    return scope if scope == "global" else f"{scope}:{scope_key or ''}"


def run_show_instructions(
    *,
    scope: InstructionScope = "global",
    scope_key: str | None = None,
) -> int:
    profile = build_user_instructions_store().get(scope=scope, scope_key=scope_key)
    if profile is None:
        print(f"No {_scope_label(scope, scope_key)} instructions configured.")
        return 0
    status = "enabled" if profile.enabled else "disabled"
    print(f"[{_scope_label(scope, profile.scope_key)}] {status}")
    print(profile.content)
    return 0


def run_set_instructions(
    *,
    content: str,
    scope: InstructionScope = "global",
    scope_key: str | None = None,
    enabled: bool = True,
) -> int:
    profile = build_user_instructions_store().set(
        content,
        scope=scope,
        scope_key=scope_key,
        enabled=enabled,
    )
    print(f"[{_scope_label(profile.scope, profile.scope_key)}]")
    print(profile.content)
    return 0


def run_clear_instructions(
    *,
    scope: InstructionScope = "global",
    scope_key: str | None = None,
) -> int:
    cleared = build_user_instructions_store().clear(scope=scope, scope_key=scope_key)
    label = _scope_label(scope, scope_key)
    print(f"{label} instructions cleared." if cleared else f"No {label} instructions configured.")
    return 0


def run_list_instructions(*, include_disabled: bool = True) -> int:
    profiles = build_user_instructions_store().list(
        include_disabled=include_disabled,
    )
    if not profiles:
        print("No user instructions configured.")
        return 0
    for profile in profiles:
        status = "enabled" if profile.enabled else "disabled"
        print(f"[{_scope_label(profile.scope, profile.scope_key)}] {status}")
        print(profile.content)
    return 0


def run_set_instructions_enabled(
    *,
    enabled: bool,
    scope: InstructionScope,
    scope_key: str | None,
) -> int:
    try:
        profile = build_user_instructions_store().set_enabled(
            enabled,
            scope=scope,
            scope_key=scope_key,
        )
    except KeyError as exc:
        print(f"Instruction error: {exc}")
        return 2
    status = "enabled" if profile.enabled else "disabled"
    print(f"[{_scope_label(profile.scope, profile.scope_key)}] {status}")
    return 0


def run_resolve_instructions(
    *,
    project_key: str | None,
    conversation_key: str | None,
    task_key: str | None,
    session_instructions: str | None,
) -> int:
    context = InstructionContext(
        project_key=project_key,
        conversation_key=conversation_key,
        task_key=task_key,
        session_instructions=session_instructions,
    )
    profiles = build_user_instructions_store().resolve(context)
    contributions = instruction_contributions(
        profiles,
        session_instructions=context.session_instructions,
    )
    rendered = render_instruction_contributions(contributions)
    if not rendered:
        print("No instructions resolve for this context.")
        return 0
    print(rendered)
    return 0
