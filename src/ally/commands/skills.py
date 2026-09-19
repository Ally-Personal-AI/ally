"""Human-facing skill manifest commands."""

from __future__ import annotations

from pathlib import Path

from ally.skills import SkillCatalog, load_skill_package
from ally.skills.loader import SkillManifestError


def run_inspect_skill(*, path: str) -> int:
    try:
        package = load_skill_package(Path(path))
    except SkillManifestError as exc:
        print(f"Skill error: {exc}")
        return 2

    manifest = package.manifest
    print(f"Skill: {manifest.id}")
    print(f"Name: {manifest.name}")
    print(f"Version: {manifest.version}")
    print(f"Schema: {manifest.schema_version}")
    print(f"Entrypoint: {manifest.entrypoint or '(declarative-only)'}")
    print("Required tools:")
    for tool in manifest.required_tools:
        print(f"  {tool}")
    print("Optional tools:")
    for tool in manifest.optional_tools:
        print(f"  {tool}")
    return 0


def run_validate_skill(*, path: str, available_tools: tuple[str, ...]) -> int:
    try:
        package = load_skill_package(Path(path))
    except SkillManifestError as exc:
        print(f"Skill error: {exc}")
        return 2

    missing = SkillCatalog.missing_required_tools(package, available_tools)
    if missing:
        print("Missing required tools:")
        for tool in missing:
            print(f"  {tool}")
        return 2

    print("Skill manifest is valid and all declared required tools are available.")
    return 0
