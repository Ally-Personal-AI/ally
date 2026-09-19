"""Human-facing skill manifest and installation commands."""

from __future__ import annotations

from pathlib import Path

from ally.skills import (
    LocalSkillManager,
    SkillCatalog,
    SkillInstallationError,
    default_skill_install_root,
    load_skill_package,
)
from ally.skills.loader import SkillManifestError
from ally.tools.builtin import build_default_tool_registry


def _manager() -> LocalSkillManager:
    return LocalSkillManager(default_skill_install_root())


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


def run_install_skill(*, path: str) -> int:
    registry = build_default_tool_registry()
    available = tuple(tool.spec.name for tool in registry.list())

    try:
        installation = _manager().install(
            Path(path),
            available_tools=available,
        )
    except (SkillInstallationError, SkillManifestError) as exc:
        print(f"Skill install error: {exc}")
        return 2

    print(
        f"Installed {installation.skill_id}@{installation.version} "
        "(disabled)"
    )
    return 0


def run_list_installed_skills() -> int:
    try:
        installations = _manager().list()
    except SkillInstallationError as exc:
        print(f"Skill error: {exc}")
        return 2

    if not installations:
        print("No installed skills.")
        return 0

    for installation in installations:
        state = "enabled" if installation.enabled else "disabled"
        print(
            f"{installation.skill_id}@{installation.version}  "
            f"{state}  {installation.installed_at.isoformat()}"
        )
    return 0


def run_enable_skill(*, skill_id: str, version: str) -> int:
    try:
        installation = _manager().set_enabled(
            skill_id,
            version,
            enabled=True,
        )
    except SkillInstallationError as exc:
        print(f"Skill error: {exc}")
        return 2

    print(f"Enabled {installation.skill_id}@{installation.version}")
    return 0


def run_disable_skill(*, skill_id: str, version: str) -> int:
    try:
        installation = _manager().set_enabled(
            skill_id,
            version,
            enabled=False,
        )
    except SkillInstallationError as exc:
        print(f"Skill error: {exc}")
        return 2

    print(f"Disabled {installation.skill_id}@{installation.version}")
    return 0


def run_uninstall_skill(*, skill_id: str, version: str) -> int:
    try:
        installation = _manager().uninstall(skill_id, version)
    except SkillInstallationError as exc:
        print(f"Skill error: {exc}")
        return 2

    print(f"Uninstalled {installation.skill_id}@{installation.version}")
    return 0
