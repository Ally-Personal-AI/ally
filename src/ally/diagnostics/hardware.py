"""Cross-platform hardware profile collection."""

from __future__ import annotations

import os
import platform
import subprocess

from pydantic import BaseModel, ConfigDict, Field


class HardwareProfile(BaseModel):
    """Small, non-sensitive machine profile for reproducible validation."""

    model_config = ConfigDict(frozen=True)

    system: str
    release: str
    machine: str
    processor: str
    python_version: str
    logical_cpu_count: int | None = Field(default=None, ge=1)
    total_memory_bytes: int | None = Field(default=None, ge=1)
    apple_model: str | None = None
    apple_chip: str | None = None


def _total_memory_bytes() -> int | None:
    if hasattr(os, "sysconf"):
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
        except (OSError, ValueError):
            return None
        total = page_size * page_count
        return total if total > 0 else None
    return None


def _sysctl_value(name: str) -> str | None:
    try:
        result = subprocess.run(
            ["sysctl", "-n", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def collect_hardware_profile() -> HardwareProfile:
    """Collect enough machine metadata to compare Ally validation runs."""

    is_darwin = platform.system() == "Darwin"
    return HardwareProfile(
        system=platform.system(),
        release=platform.release(),
        machine=platform.machine(),
        processor=platform.processor(),
        python_version=platform.python_version(),
        logical_cpu_count=os.cpu_count(),
        total_memory_bytes=_total_memory_bytes(),
        apple_model=_sysctl_value("hw.model") if is_darwin else None,
        apple_chip=(
            _sysctl_value("machdep.cpu.brand_string") if is_darwin else None
        ),
    )
