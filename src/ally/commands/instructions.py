"""CLI operations for the private user instruction profile."""

from __future__ import annotations

from ally.commands._storage import build_user_instructions_store


def run_show_instructions() -> int:
    profile = build_user_instructions_store().get()
    if profile is None:
        print("No user instructions configured.")
        return 0
    print(profile.content)
    return 0


def run_set_instructions(*, content: str) -> int:
    profile = build_user_instructions_store().set(content)
    print(profile.content)
    return 0


def run_clear_instructions() -> int:
    cleared = build_user_instructions_store().clear()
    print("User instructions cleared." if cleared else "No user instructions configured.")
    return 0
