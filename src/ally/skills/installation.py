"""Local-only skill installation lifecycle.

Installation validates and copies packages. It never imports skill entrypoints.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from ally.config import default_paths
from ally.skills.catalog import SkillCatalog
from ally.skills.loader import SkillManifestError, load_skill_package
from ally.skills.models import SkillInstallation, SkillPackage

_METADATA_NAME = ".ally-installation.json"
_SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class SkillInstallationError(ValueError):
    """Raised when a local skill cannot be installed or managed safely."""


def default_skill_install_root() -> Path:
    """Return Ally-owned local package storage."""

    return default_paths().data_dir / "skills"


def _validate_package_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.name == _METADATA_NAME:
            raise SkillInstallationError(
                f"skill package contains reserved metadata file: {path}"
            )
        if path.is_symlink():
            raise SkillInstallationError(
                f"skill packages may not contain symlinks: {path}"
            )
        if not path.is_file() and not path.is_dir():
            raise SkillInstallationError(
                f"skill packages may contain only regular files/directories: {path}"
            )


def _metadata_path(package_root: Path) -> Path:
    return package_root / _METADATA_NAME


def _write_metadata(path: Path, installation: SkillInstallation) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    rendered = (
        json.dumps(
            installation.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_metadata(path: Path) -> SkillInstallation:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillInstallationError(
            f"could not read skill installation metadata: {path}"
        ) from exc

    try:
        return SkillInstallation.model_validate_json(raw)
    except ValidationError as exc:
        raise SkillInstallationError(
            f"invalid skill installation metadata: {path}"
        ) from exc


def _validate_selector(value: str, *, label: str, pattern: re.Pattern[str]) -> str:
    if pattern.fullmatch(value) is None:
        raise SkillInstallationError(f"invalid {label}: {value}")
    return value


class LocalSkillManager:
    """Manage copied skill packages without importing executable code."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def _package_root(self, skill_id: str, version: str) -> Path:
        safe_id = _validate_selector(
            skill_id,
            label="skill ID",
            pattern=_SKILL_ID_PATTERN,
        )
        safe_version = _validate_selector(
            version,
            label="skill version",
            pattern=_VERSION_PATTERN,
        )
        return self.root / safe_id / safe_version

    def install(
        self,
        source: Path,
        *,
        available_tools: tuple[str, ...],
    ) -> SkillInstallation:
        package = load_skill_package(source)
        source_root = Path(package.root)
        _validate_package_tree(source_root)

        missing = SkillCatalog.missing_required_tools(package, available_tools)
        if missing:
            names = ", ".join(missing)
            raise SkillInstallationError(
                f"missing required tools: {names}"
            )

        destination = self._package_root(
            package.manifest.id,
            package.manifest.version,
        )
        if destination.exists():
            raise SkillInstallationError(
                "skill version is already installed: "
                f"{package.manifest.id}@{package.manifest.version}"
            )

        installation = SkillInstallation(
            id=uuid4(),
            skill_id=package.manifest.id,
            version=package.manifest.version,
            source_uri=source_root.as_uri(),
            installed_at=datetime.now(UTC),
            enabled=False,
        )

        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".install-{uuid4().hex}"
        try:
            shutil.copytree(source_root, staging)
            _write_metadata(_metadata_path(staging), installation)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, destination)
        except OSError as exc:
            raise SkillInstallationError(
                f"could not install skill package: {exc}"
            ) from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging)

        return installation

    def list(self) -> tuple[SkillInstallation, ...]:
        if not self.root.exists():
            return ()

        installations: list[SkillInstallation] = []
        for metadata in sorted(self.root.glob(f"*/*/{_METADATA_NAME}")):
            installations.append(_load_metadata(metadata))
        return tuple(
            sorted(
                installations,
                key=lambda item: (item.skill_id, item.version),
            )
        )

    def get(
        self,
        skill_id: str,
        version: str,
    ) -> SkillInstallation | None:
        path = self._package_root(skill_id, version) / _METADATA_NAME
        if not path.is_file():
            return None
        return _load_metadata(path)

    def set_enabled(
        self,
        skill_id: str,
        version: str,
        *,
        enabled: bool,
    ) -> SkillInstallation:
        package_root = self._package_root(skill_id, version)
        metadata = _metadata_path(package_root)
        current = self.get(skill_id, version)
        if current is None:
            raise SkillInstallationError(
                f"skill is not installed: {skill_id}@{version}"
            )

        if enabled:
            for installation in self.list():
                if (
                    installation.skill_id == skill_id
                    and installation.version != version
                    and installation.enabled
                ):
                    self.set_enabled(
                        skill_id,
                        installation.version,
                        enabled=False,
                    )

        updated = current.model_copy(update={"enabled": enabled})
        try:
            _write_metadata(metadata, updated)
        except OSError as exc:
            raise SkillInstallationError(
                f"could not update skill installation metadata: {exc}"
            ) from exc
        return updated

    def uninstall(self, skill_id: str, version: str) -> SkillInstallation:
        installation = self.get(skill_id, version)
        if installation is None:
            raise SkillInstallationError(
                f"skill is not installed: {skill_id}@{version}"
            )

        package_root = self._package_root(skill_id, version)
        try:
            shutil.rmtree(package_root)
        except OSError as exc:
            raise SkillInstallationError(
                f"could not uninstall skill package: {exc}"
            ) from exc

        skill_root = package_root.parent
        with suppress(OSError):
            skill_root.rmdir()

        return installation

    def load_package(
        self,
        skill_id: str,
        version: str,
    ) -> SkillPackage:
        """Validate an installed package as data; never import its entrypoint."""

        package_root = self._package_root(skill_id, version)
        try:
            package = load_skill_package(package_root)
        except SkillManifestError as exc:
            raise SkillInstallationError(str(exc)) from exc

        if (
            package.manifest.id != skill_id
            or package.manifest.version != version
        ):
            raise SkillInstallationError(
                "installed skill manifest identity does not match its path: "
                f"{skill_id}@{version}"
            )
        return package
