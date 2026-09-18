"""Local persistence infrastructure."""

from __future__ import annotations

from pathlib import Path

from ally.config import default_paths


def default_database_path() -> Path:
    """Return the default local Ally database path."""

    return default_paths().data_dir / "ally.sqlite3"
