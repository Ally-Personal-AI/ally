"""Deterministic, opt-in launchd integration for Ally's bounded service cycle."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ally.config import default_paths

LAUNCHD_LABEL = "ai.ally.proactive-service"
LAUNCHD_INTERVAL_SECONDS = 60
LAUNCHCTL_PATH = Path("/bin/launchctl")


class ManagedServiceError(RuntimeError):
    """Raised when a managed-service operation cannot be completed safely."""


@dataclass(frozen=True)
class LaunchctlResult:
    returncode: int
    stdout: str = ""


class LaunchctlRunner(Protocol):
    def run(self, arguments: Sequence[str]) -> LaunchctlResult: ...


class SubprocessLaunchctlRunner:
    """Run launchctl directly, without a shell or inherited input."""

    def run(self, arguments: Sequence[str]) -> LaunchctlResult:
        try:
            result = subprocess.run(
                [str(LAUNCHCTL_PATH), *arguments],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ManagedServiceError("launchctl could not be executed") from exc
        return LaunchctlResult(result.returncode, result.stdout)


@dataclass(frozen=True)
class ManagedServicePaths:
    plist: Path
    stdout_log: Path
    stderr_log: Path


@dataclass(frozen=True)
class ManagedServiceStatus:
    supported: bool
    configured: bool
    definition_matches: bool
    loaded: bool
    running: bool
    label: str
    plist_path: Path

    def as_dict(self) -> dict[str, bool | str]:
        return {
            "supported": self.supported,
            "configured": self.configured,
            "definition_matches": self.definition_matches,
            "loaded": self.loaded,
            "running": self.running,
            "label": self.label,
            "plist_path": str(self.plist_path),
        }


def default_managed_service_paths() -> ManagedServicePaths:
    data_dir = default_paths().data_dir
    log_dir = data_dir / "service" / "logs"
    return ManagedServicePaths(
        plist=Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist",
        stdout_log=log_dir / "stdout.log",
        stderr_log=log_dir / "stderr.log",
    )


class MacOSLaunchdService:
    """Manage one launch agent while keeping the application cycle bounded."""

    def __init__(
        self,
        *,
        paths: ManagedServicePaths | None = None,
        runner: LaunchctlRunner | None = None,
        executable: Path | None = None,
        uid: int | None = None,
        supported: bool | None = None,
    ) -> None:
        self.paths = paths or default_managed_service_paths()
        self.runner = runner or SubprocessLaunchctlRunner()
        self.executable = (executable or Path(sys.executable)).resolve()
        self.uid = _current_uid() if uid is None else uid
        self.supported = sys.platform == "darwin" if supported is None else supported

    @property
    def domain_target(self) -> str:
        return f"gui/{self.uid}"

    @property
    def service_target(self) -> str:
        return f"{self.domain_target}/{LAUNCHD_LABEL}"

    def definition(self) -> dict[str, object]:
        """Return the complete deterministic launch-agent definition."""

        return {
            "Label": LAUNCHD_LABEL,
            "LowPriorityIO": True,
            "ProcessType": "Background",
            "ProgramArguments": [
                str(self.executable),
                "-m",
                "ally.cli",
                "service",
                "cycle",
                "--json",
            ],
            "RunAtLoad": True,
            "StandardErrorPath": str(self.paths.stderr_log.resolve()),
            "StandardOutPath": str(self.paths.stdout_log.resolve()),
            "StartInterval": LAUNCHD_INTERVAL_SECONDS,
            "Umask": 0o077,
        }

    def definition_bytes(self) -> bytes:
        return plistlib.dumps(
            self.definition(),
            fmt=plistlib.FMT_XML,
            sort_keys=True,
        )

    def status(self) -> ManagedServiceStatus:
        configured = self.paths.plist.is_file()
        definition_matches = configured and self._installed_definition_matches()
        loaded = False
        running = False
        if self.supported:
            result = self.runner.run(("print", self.service_target))
            loaded = result.returncode == 0
            running = loaded and "state = running" in result.stdout
        return ManagedServiceStatus(
            supported=self.supported,
            configured=configured,
            definition_matches=definition_matches,
            loaded=loaded,
            running=running,
            label=LAUNCHD_LABEL,
            plist_path=self.paths.plist,
        )

    def install(self) -> ManagedServiceStatus:
        self._require_supported()
        self._require_executable()
        expected = self.definition_bytes()
        published_identity: tuple[int, int] | None = None
        if self.paths.plist.exists() or self.paths.plist.is_symlink():
            if not self._installed_definition_matches():
                raise ManagedServiceError(
                    "managed-service definition already exists and differs from Ally's"
                )
        else:
            self.paths.plist.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.paths.stdout_log.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            published_identity = self._publish_definition(expected)

        current = self.status()
        if not current.loaded:
            result = self.runner.run(
                ("bootstrap", self.domain_target, str(self.paths.plist.resolve()))
            )
            if result.returncode != 0:
                if published_identity is not None:
                    self._unlink_if_identity(published_identity)
                raise ManagedServiceError("launchd could not load Ally's managed service")
        return self.status()

    def start(self) -> ManagedServiceStatus:
        self._require_supported()
        self._require_owned_definition()
        current = self.status()
        if not current.loaded:
            result = self.runner.run(
                ("bootstrap", self.domain_target, str(self.paths.plist.resolve()))
            )
            if result.returncode != 0:
                raise ManagedServiceError("launchd could not load Ally's managed service")
        else:
            result = self.runner.run(("kickstart", "-k", self.service_target))
            if result.returncode != 0:
                raise ManagedServiceError("launchd could not start Ally's managed service")
        return self.status()

    def stop(self) -> ManagedServiceStatus:
        self._require_supported()
        self._require_owned_definition()
        if self.status().loaded:
            result = self.runner.run(("bootout", self.service_target))
            if result.returncode != 0:
                raise ManagedServiceError("launchd could not stop Ally's managed service")
        return self.status()

    def uninstall(self) -> ManagedServiceStatus:
        self._require_supported()
        if self.paths.plist.exists() or self.paths.plist.is_symlink():
            self._require_owned_definition()
        if self.status().loaded:
            result = self.runner.run(("bootout", self.service_target))
            if result.returncode != 0:
                raise ManagedServiceError("launchd could not unload Ally's managed service")
        self.paths.plist.unlink(missing_ok=True)
        return self.status()

    def _require_supported(self) -> None:
        if not self.supported:
            raise ManagedServiceError("managed-service changes are supported only on macOS")

    def _require_executable(self) -> None:
        if not self.executable.is_absolute() or not self.executable.is_file():
            raise ManagedServiceError("the Ally Python executable is unavailable")
        if not os.access(self.executable, os.X_OK):
            raise ManagedServiceError("the Ally Python executable is not executable")

    def _installed_definition_matches(self) -> bool:
        if self.paths.plist.is_symlink():
            return False
        try:
            return self.paths.plist.read_bytes() == self.definition_bytes()
        except OSError:
            return False

    def _require_owned_definition(self) -> None:
        if not self.paths.plist.is_file() or not self._installed_definition_matches():
            raise ManagedServiceError(
                "Ally's managed-service definition is missing or has been modified"
            )

    def _publish_definition(self, payload: bytes) -> tuple[int, int]:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{LAUNCHD_LABEL}.",
            suffix=".tmp",
            dir=self.paths.plist.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            try:
                os.link(temporary, self.paths.plist)
            except FileExistsError as exc:
                raise ManagedServiceError(
                    "managed-service definition appeared during installation"
                ) from exc
            except OSError as exc:
                raise ManagedServiceError(
                    "managed-service definition could not be published safely"
                ) from exc
            published = self.paths.plist.stat(follow_symlinks=False)
            return published.st_dev, published.st_ino
        finally:
            temporary.unlink(missing_ok=True)

    def _unlink_if_identity(self, identity: tuple[int, int]) -> None:
        try:
            current = self.paths.plist.stat(follow_symlinks=False)
        except FileNotFoundError:
            return
        if (current.st_dev, current.st_ino) == identity:
            self.paths.plist.unlink()


def _current_uid() -> int:
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return 0
    return getuid()
