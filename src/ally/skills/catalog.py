"""In-memory catalog and dependency checks for loaded skills."""

from __future__ import annotations

from collections.abc import Iterable

from ally.skills.models import SkillPackage


class SkillCatalog:
    """Explicit catalog of skill packages available to a runtime."""

    def __init__(self) -> None:
        self._packages: dict[str, SkillPackage] = {}

    def register(self, package: SkillPackage) -> None:
        skill_id = package.manifest.id
        if skill_id in self._packages:
            raise ValueError(f"Skill already registered: {skill_id}")
        self._packages[skill_id] = package

    def get(self, skill_id: str) -> SkillPackage | None:
        return self._packages.get(skill_id)

    def list(self) -> tuple[SkillPackage, ...]:
        return tuple(self._packages[key] for key in sorted(self._packages))

    @staticmethod
    def missing_required_tools(
        package: SkillPackage,
        available_tools: Iterable[str],
    ) -> tuple[str, ...]:
        available = set(available_tools)
        return tuple(
            sorted(
                tool
                for tool in package.manifest.required_tools
                if tool not in available
            )
        )
