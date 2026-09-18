"""Local configuration and data-path boundaries for Ally."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel, ConfigDict, Field


APP_NAME = "Ally"
APP_AUTHOR = "AllyPersonalAI"


class AllyPaths(BaseModel):
    """Filesystem locations used by an Ally installation.

    Runtime and personal data are intentionally kept outside the source tree.
    """

    model_config = ConfigDict(frozen=True)

    config_dir: Path = Field(description="Non-secret Ally configuration.")
    data_dir: Path = Field(description="Personal state, memory, and runtime data.")


def default_paths() -> AllyPaths:
    """Return OS-appropriate default local paths for Ally."""

    return AllyPaths(
        config_dir=Path(user_config_dir(APP_NAME, APP_AUTHOR)),
        data_dir=Path(user_data_dir(APP_NAME, APP_AUTHOR)),
    )
