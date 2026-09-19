"""Atomic local storage for non-secret Ally configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from ally.config import default_paths
from ally.configuration.models import AllyConfig


class ConfigFileError(ValueError):
    """Raised when an Ally configuration file cannot be loaded safely."""


def default_config_path() -> Path:
    """Return the default versioned Ally config document path."""

    return default_paths().config_dir / "config.json"


class FileConfigStore:
    """Read and atomically initialize/replace non-secret Ally configuration."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def load(self) -> AllyConfig:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigFileError(f"could not read config: {self.path}") from exc

        try:
            return AllyConfig.model_validate_json(raw)
        except ValidationError as exc:
            raise ConfigFileError(f"invalid Ally config: {exc}") from exc

    def load_or_default(self) -> AllyConfig:
        if not self.path.exists():
            return AllyConfig()
        return self.load()

    def initialize(self, config: AllyConfig | None = None) -> AllyConfig:
        if self.path.exists():
            raise FileExistsError(f"config already exists: {self.path}")
        value = config or AllyConfig()
        self._write_atomic(value)
        return value

    def replace(self, config: AllyConfig) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"config does not exist: {self.path}")
        self._write_atomic(config)

    def _write_atomic(self, config: AllyConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f".{self.path.name}.{uuid4().hex}.tmp"
        )
        rendered = (
            json.dumps(
                config.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        try:
            temporary.write_text(rendered, encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
