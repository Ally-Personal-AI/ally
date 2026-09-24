"""Ally-owned catalog and active selection for validated runtime profiles."""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ally.config import default_paths
from ally.runtime_profiles.models import (
    ValidatedRuntimeProfile,
    ValidatedRuntimeProfileError,
    load_validated_runtime_profile,
    verify_validated_runtime_profile,
)

_MAX_SELECTION_BYTES = 1024 * 1024


class RuntimeProfileCatalogError(ValueError):
    """Raised when installed profile state cannot be trusted."""


class ActiveRuntimeProfileSelection(BaseModel):
    """Hash-bound reference to one installed validated runtime profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    selected_at: datetime
    profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_selection(self) -> ActiveRuntimeProfileSelection:
        if self.selected_at.tzinfo is None or self.selected_at.utcoffset() is None:
            raise ValueError("runtime profile selection timestamp must include timezone")
        return self


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class RuntimeProfileCatalog:
    """Filesystem catalog for installed, evidence-verified runtime profiles."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().absolute()
        self.selection_path = self.root / "active.json"

    def _ensure_root(self) -> None:
        try:
            if self.root.exists() and self.root.is_symlink():
                raise RuntimeProfileCatalogError(
                    "runtime profile catalog root must not be a symlink"
                )
            self.root.mkdir(parents=True, exist_ok=True)
            with suppress(OSError):
                self.root.chmod(0o700)
        except RuntimeProfileCatalogError:
            raise
        except OSError as exc:
            raise RuntimeProfileCatalogError(
                "runtime profile catalog is unavailable"
            ) from exc

    def _profile_path(self, profile_id: str) -> Path:
        if (
            len(profile_id) != 64
            or any(character not in "0123456789abcdef" for character in profile_id)
        ):
            raise RuntimeProfileCatalogError("invalid runtime profile ID")
        return self.root / f"{profile_id}.json"

    @staticmethod
    def _reject_symlink(path: Path, label: str) -> None:
        expanded = path.expanduser()
        if expanded.is_symlink():
            raise RuntimeProfileCatalogError(f"{label} must not be a symlink")

    def install(
        self,
        *,
        profile_path: Path,
        validation_path: Path,
        privacy_path: Path,
        workflow_path: Path,
    ) -> Path:
        """Install only a profile that re-verifies against all exact evidence."""

        for path, label in (
            (profile_path, "runtime profile"),
            (validation_path, "capability evidence"),
            (privacy_path, "privacy evidence"),
            (workflow_path, "workflow evidence"),
        ):
            self._reject_symlink(path, label)

        try:
            profile = load_validated_runtime_profile(profile_path)
            verify_validated_runtime_profile(
                profile,
                validation_path=validation_path,
                privacy_path=privacy_path,
                workflow_path=workflow_path,
            )
        except (OSError, ValueError) as exc:
            raise RuntimeProfileCatalogError(
                "runtime profile failed source-evidence verification"
            ) from exc

        self._ensure_root()
        destination = self._profile_path(profile.profile_id)
        if destination.is_symlink():
            raise RuntimeProfileCatalogError(
                "installed runtime profile path must not be a symlink"
            )
        if destination.exists():
            try:
                existing = load_validated_runtime_profile(destination)
                verify_validated_runtime_profile(
                    existing,
                    validation_path=validation_path,
                    privacy_path=privacy_path,
                    workflow_path=workflow_path,
                )
            except (OSError, ValueError) as exc:
                raise RuntimeProfileCatalogError(
                    "existing runtime profile ID does not match verified source evidence"
                ) from exc
            return destination

        temporary = self.root / f".{profile.profile_id}.{uuid4().hex}.tmp"
        try:
            try:
                temporary.write_text(
                    json.dumps(
                        profile.model_dump(mode="json"),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                with suppress(OSError):
                    temporary.chmod(0o600)
                try:
                    os.link(temporary, destination)
                except FileExistsError as exc:
                    raise RuntimeProfileCatalogError(
                        "runtime profile appeared concurrently during installation"
                    ) from exc
                with suppress(OSError):
                    destination.chmod(0o600)
            except RuntimeProfileCatalogError:
                raise
            except OSError as exc:
                raise RuntimeProfileCatalogError(
                    "runtime profile could not be installed"
                ) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        return destination

    def list(self) -> tuple[ValidatedRuntimeProfile, ...]:
        """Load every installed profile strictly in deterministic ID order."""

        try:
            if not self.root.exists():
                return ()
            if self.root.is_symlink():
                raise RuntimeProfileCatalogError(
                    "runtime profile catalog root must not be a symlink"
                )
            profiles: list[ValidatedRuntimeProfile] = []
            for path in sorted(self.root.glob("[0-9a-f]" * 64 + ".json")):
                if path.is_symlink():
                    raise RuntimeProfileCatalogError(
                        "installed runtime profiles must not be symlinks"
                    )
                try:
                    profile = load_validated_runtime_profile(path)
                except ValidatedRuntimeProfileError as exc:
                    raise RuntimeProfileCatalogError(
                        "installed runtime profile is invalid"
                    ) from exc
                if path.stem != profile.profile_id:
                    raise RuntimeProfileCatalogError(
                        "installed runtime profile ID does not match its filename"
                    )
                profiles.append(profile)
            return tuple(profiles)
        except RuntimeProfileCatalogError:
            raise
        except OSError as exc:
            raise RuntimeProfileCatalogError(
                "runtime profile catalog could not be read"
            ) from exc

    def get(self, profile_id: str) -> ValidatedRuntimeProfile:
        """Load one installed profile by deterministic ID."""

        path = self._profile_path(profile_id)
        if path.is_symlink():
            raise RuntimeProfileCatalogError(
                "installed runtime profile must not be a symlink"
            )
        if not path.is_file():
            raise RuntimeProfileCatalogError("runtime profile is not installed")
        try:
            profile = load_validated_runtime_profile(path)
        except ValidatedRuntimeProfileError as exc:
            raise RuntimeProfileCatalogError(
                "installed runtime profile is invalid"
            ) from exc
        if profile.profile_id != profile_id:
            raise RuntimeProfileCatalogError(
                "installed runtime profile ID does not match its filename"
            )
        return profile

    def select(self, profile_id: str) -> ActiveRuntimeProfileSelection:
        """Select one installed profile and bind selection to its exact bytes."""

        profile = self.get(profile_id)
        path = self._profile_path(profile.profile_id)
        try:
            digest = _sha256(path)
        except OSError as exc:
            raise RuntimeProfileCatalogError(
                "runtime profile could not be read for selection"
            ) from exc
        selection = ActiveRuntimeProfileSelection(
            selected_at=datetime.now(UTC),
            profile_id=profile.profile_id,
            profile_sha256=digest,
        )
        self._ensure_root()
        temporary = self.root / f".active.json.{uuid4().hex}.tmp"
        try:
            try:
                temporary.write_text(
                    json.dumps(
                        selection.model_dump(mode="json"),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                with suppress(OSError):
                    temporary.chmod(0o600)
                os.replace(temporary, self.selection_path)
                with suppress(OSError):
                    self.selection_path.chmod(0o600)
            except OSError as exc:
                raise RuntimeProfileCatalogError(
                    "active runtime profile selection could not be written"
                ) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        return selection

    def _load_selection(self) -> ActiveRuntimeProfileSelection:
        if self.selection_path.is_symlink():
            raise RuntimeProfileCatalogError(
                "active runtime profile selection must not be a symlink"
            )
        if not self.selection_path.is_file():
            raise RuntimeProfileCatalogError("no active runtime profile is selected")
        try:
            if self.selection_path.stat().st_size > _MAX_SELECTION_BYTES:
                raise RuntimeProfileCatalogError(
                    "active runtime profile selection exceeds the size limit"
                )
            return ActiveRuntimeProfileSelection.model_validate_json(
                self.selection_path.read_text(encoding="utf-8")
            )
        except RuntimeProfileCatalogError:
            raise
        except (OSError, UnicodeError, ValidationError) as exc:
            raise RuntimeProfileCatalogError(
                "active runtime profile selection is invalid"
            ) from exc

    def selection(self) -> ActiveRuntimeProfileSelection | None:
        """Return validated active selection metadata, or None when unset."""

        if not self.selection_path.exists():
            return None
        return self._load_selection()

    def active(self) -> ValidatedRuntimeProfile:
        """Resolve active selection and fail if the installed profile changed."""

        selection = self._load_selection()
        path = self._profile_path(selection.profile_id)
        profile = self.get(selection.profile_id)
        try:
            digest = _sha256(path)
        except OSError as exc:
            raise RuntimeProfileCatalogError(
                "active runtime profile could not be read"
            ) from exc
        if digest != selection.profile_sha256:
            raise RuntimeProfileCatalogError(
                "active runtime profile content changed after selection"
            )
        return profile

    def deselect(self) -> bool:
        """Clear active selection without deleting any installed profile."""

        try:
            if self.selection_path.is_symlink():
                raise RuntimeProfileCatalogError(
                    "active runtime profile selection must not be a symlink"
                )
            if not self.selection_path.exists():
                return False
            self.selection_path.unlink()
            return True
        except RuntimeProfileCatalogError:
            raise
        except OSError as exc:
            raise RuntimeProfileCatalogError(
                "active runtime profile selection could not be cleared"
            ) from exc

    def remove(self, profile_id: str) -> bool:
        """Remove an inactive installed profile only."""

        selection = self.selection()
        if selection is not None and selection.profile_id == profile_id:
            raise RuntimeProfileCatalogError(
                "cannot remove the active runtime profile; deselect it first"
            )
        path = self._profile_path(profile_id)
        if path.is_symlink():
            raise RuntimeProfileCatalogError(
                "installed runtime profile must not be a symlink"
            )
        try:
            if not path.exists():
                return False
            path.unlink()
            return True
        except OSError as exc:
            raise RuntimeProfileCatalogError(
                "runtime profile could not be removed"
            ) from exc


def default_runtime_profile_catalog() -> RuntimeProfileCatalog:
    """Return the user's Ally-owned non-secret runtime-profile catalog."""

    return RuntimeProfileCatalog(default_paths().config_dir / "runtime-profiles")


def resolve_active_runtime_profile() -> ValidatedRuntimeProfile:
    """Reusable production resolver for future runtime/UI composition."""

    return default_runtime_profile_catalog().active()
