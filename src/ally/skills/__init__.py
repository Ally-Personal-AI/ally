"""Declarative Ally skill packages."""

from ally.skills.catalog import SkillCatalog
from ally.skills.installation import (
    LocalSkillManager,
    SkillInstallationError,
    default_skill_install_root,
)
from ally.skills.loader import load_skill_package
from ally.skills.models import (
    SkillConfigField,
    SkillInstallation,
    SkillManifest,
    SkillPackage,
)

__all__ = [
    "LocalSkillManager",
    "SkillCatalog",
    "SkillConfigField",
    "SkillInstallationError",
    "SkillInstallation",
    "SkillManifest",
    "SkillPackage",
    "default_skill_install_root",
    "load_skill_package",
]
