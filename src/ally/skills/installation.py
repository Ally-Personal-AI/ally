"""Local-only skill installation lifecycle.

Installation validates and copies packages. It never imports skill entrypoints.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from ally.config import default_paths
from ally.skills.catalog import SkillCatalog
from ally.skills.loader import SkillManifestError, load_skill_package
from ally.skills.models import SkillInstallation, SkillPackage

_METADATA_NAME = ".ally-installation.json"


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


class LocalSkillManager:
    """Manage copied skill packages without importing executable code."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

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

        destination = (
            self.root
            / package.manifest.id
            / package.manifest.version
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
        path = self.root / skill_id / version / _METADATA_NAME
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
        package_root = self.root / skill_id / version
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
        _write_metadata(metadata, updated)
        return updated

    def uninstall(self, skill_id: str, version: str) -> SkillInstallation:
        installation = self.get(skill_id, version)
        if installation is None:
            raise SkillInstallationError(
                f"skill is not installed: {skill_id}@{version}"
            )

        package_root = self.root / skill_id / version
        shutil.rmtree(package_root)

        skill_root = package_root.parent
        try:
            skill_root.rmdir()
        except OSError:
            pass

        return installation

    def load_package(
        self,
        skill_id: str,
        version: str,
    ) -> SkillPackage:
        """Validate an installed package as data; never import its entrypoint."""

        package_root = self.root / skill_id / version
        try:
            return load_skill_package(package_root)
        except SkillManifestError as exc:
            raise SkillInstallationError(str(exc)) from exc
