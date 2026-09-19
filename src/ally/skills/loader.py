"""Load and validate declarative skill packages."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import ValidationError

from ally.skills.models import SkillManifest, SkillPackage


class SkillManifestError(ValueError):
    """Raised when a skill package cannot be loaded safely."""


def load_skill_package(root: Path) -> SkillPackage:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise SkillManifestError(f"Skill package is not a directory: {resolved}")

    manifest_path = resolved / "skill.toml"
    if not manifest_path.is_file():
        raise SkillManifestError(f"Missing skill manifest: {manifest_path}")

    try:
        with manifest_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise SkillManifestError(f"Invalid TOML in {manifest_path}: {exc}") from exc

    try:
        manifest = SkillManifest.model_validate(raw)
    except ValidationError as exc:
        raise SkillManifestError(f"Invalid skill manifest: {exc}") from exc

    return SkillPackage(root=str(resolved), manifest=manifest)
