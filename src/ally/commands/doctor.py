"""Environment diagnostics for Ally."""

from __future__ import annotations

from ally import __version__
from ally.config import default_paths


def run_doctor() -> int:
    paths = default_paths()
    print(f"Ally {__version__}")
    print(f"Config: {paths.config_dir}")
    print(f"Data:   {paths.data_dir}")
    return 0
