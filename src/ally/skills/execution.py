"""Process-isolated execution for explicitly enabled installed skills."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from pydantic import JsonValue, ValidationError

from ally.skills.audit import SkillExecutionAuditStore
from ally.skills.installation import LocalSkillManager, SkillInstallationError
from ally.skills.models import (
    SkillExecutionResult,
    SkillWorkerRequest,
    SkillWorkerResponse,
)

DEFAULT_SKILL_TIMEOUT_SECONDS = 5
MAX_SKILL_TIMEOUT_SECONDS = 60
MAX_SKILL_INPUT_BYTES = 64 * 1024
MAX_SKILL_OUTPUT_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 4096


class SkillExecutionError(ValueError):
    """Raised before execution when an installed skill is not runnable."""


def _minimal_environment() -> dict[str, str]:
    environment = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR"):
            value = os.environ.get(name)
            if value is not None:
                environment[name] = value
    return environment


def _validate_runtime_tree(root: Path) -> None:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise SkillExecutionError(f"installed skill directory is missing: {resolved}")

    for path in resolved.rglob("*"):
        if path.is_symlink():
            raise SkillExecutionError(
                f"installed skill contains a symlink: {path}"
            )
        if not path.is_file() and not path.is_dir():
            raise SkillExecutionError(
                f"installed skill contains a special file: {path}"
            )


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def _drain_stream(
    stream: BinaryIO,
    target: bytearray,
    overflow: threading.Event,
    process: subprocess.Popen[bytes],
) -> None:
    while True:
        chunk = stream.read(_READ_CHUNK_BYTES)
        if not chunk:
            return

        remaining = MAX_SKILL_OUTPUT_BYTES - len(target)
        if remaining <= 0:
            overflow.set()
            _kill_process(process)
            return

        if len(chunk) > remaining:
            target.extend(chunk[:remaining])
            overflow.set()
            _kill_process(process)
            return

        target.extend(chunk)


class SkillProcessExecutor:
    """Execute one Python skill in a separate interpreter process."""

    def execute(
        self,
        *,
        skill_id: str,
        version: str,
        package_root: Path,
        entrypoint: str,
        input_data: dict[str, JsonValue],
        timeout_seconds: int = DEFAULT_SKILL_TIMEOUT_SECONDS,
    ) -> SkillExecutionResult:
        if timeout_seconds < 1 or timeout_seconds > MAX_SKILL_TIMEOUT_SECONDS:
            raise SkillExecutionError(
                "timeout_seconds must be between 1 and "
                f"{MAX_SKILL_TIMEOUT_SECONDS}"
            )

        _validate_runtime_tree(package_root)
        request = SkillWorkerRequest(input=input_data)
        request_bytes = request.model_dump_json().encode("utf-8")
        if len(request_bytes) > MAX_SKILL_INPUT_BYTES:
            raise SkillExecutionError(
                f"skill input exceeds {MAX_SKILL_INPUT_BYTES} bytes"
            )

        worker = Path(__file__).with_name("_worker.py").resolve()
        command = [
            sys.executable,
            "-I",
            str(worker),
            str(package_root.resolve()),
            entrypoint,
        ]

        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()

        with tempfile.TemporaryFile() as input_file:
            input_file.write(request_bytes)
            input_file.seek(0)

            try:
                process = subprocess.Popen(
                    command,
                    stdin=input_file,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=package_root,
                    env=_minimal_environment(),
                    close_fds=True,
                    start_new_session=os.name == "posix",
                    creationflags=(
                        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        if os.name == "nt"
                        else 0
                    ),
                )
            except OSError:
                return self._result(
                    skill_id=skill_id,
                    version=version,
                    status="failed",
                    error_class="SkillProcessLaunchError",
                    exit_code=None,
                    started_at=started_at,
                    started_monotonic=started_monotonic,
                )

            assert process.stdout is not None
            assert process.stderr is not None
            stdout = bytearray()
            stderr = bytearray()
            overflow = threading.Event()
            stdout_thread = threading.Thread(
                target=_drain_stream,
                args=(process.stdout, stdout, overflow, process),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_drain_stream,
                args=(process.stderr, stderr, overflow, process),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            timed_out = False
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process(process)
                process.wait()

            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            if stdout_thread.is_alive() or stderr_thread.is_alive():
                _kill_process(process)
                return self._result(
                    skill_id=skill_id,
                    version=version,
                    status="protocol_error",
                    error_class="SkillPipeDrainError",
                    exit_code=process.returncode,
                    started_at=started_at,
                    started_monotonic=started_monotonic,
                )

        if timed_out:
            return self._result(
                skill_id=skill_id,
                version=version,
                status="timed_out",
                error_class="SkillExecutionTimeout",
                exit_code=process.returncode,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )

        if overflow.is_set():
            return self._result(
                skill_id=skill_id,
                version=version,
                status="output_limit",
                error_class="SkillOutputLimitExceeded",
                exit_code=process.returncode,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )

        if stderr:
            return self._result(
                skill_id=skill_id,
                version=version,
                status="protocol_error",
                error_class="SkillProtocolError",
                exit_code=process.returncode,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )

        try:
            response = SkillWorkerResponse.model_validate_json(bytes(stdout))
        except ValidationError:
            return self._result(
                skill_id=skill_id,
                version=version,
                status="protocol_error",
                error_class="SkillProtocolError",
                exit_code=process.returncode,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )

        if response.ok:
            if process.returncode != 0:
                return self._result(
                    skill_id=skill_id,
                    version=version,
                    status="protocol_error",
                    error_class="SkillProcessExitError",
                    exit_code=process.returncode,
                    started_at=started_at,
                    started_monotonic=started_monotonic,
                )
            return self._result(
                skill_id=skill_id,
                version=version,
                status="succeeded",
                result=response.result,
                error_class=None,
                exit_code=process.returncode,
                started_at=started_at,
                started_monotonic=started_monotonic,
            )

        return self._result(
            skill_id=skill_id,
            version=version,
            status="failed",
            error_class=response.error_class,
            exit_code=process.returncode,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )

    @staticmethod
    def _result(
        *,
        skill_id: str,
        version: str,
        status: str,
        started_at: datetime,
        started_monotonic: float,
        error_class: str | None,
        exit_code: int | None,
        result: JsonValue | None = None,
    ) -> SkillExecutionResult:
        finished_at = datetime.now(UTC)
        duration_ms = max(
            0,
            int((time.monotonic() - started_monotonic) * 1000),
        )
        return SkillExecutionResult.model_validate(
            {
                "skill_id": skill_id,
                "version": version,
                "status": status,
                "result": result,
                "error_class": error_class,
                "exit_code": exit_code,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
            }
        )


class InstalledSkillRuntime:
    """Execute an enabled installed skill without importing it into Ally Core."""

    def __init__(
        self,
        manager: LocalSkillManager,
        audit: SkillExecutionAuditStore,
        executor: SkillProcessExecutor | None = None,
    ) -> None:
        self._manager = manager
        self._audit = audit
        self._executor = executor or SkillProcessExecutor()

    def execute(
        self,
        skill_id: str,
        version: str,
        *,
        input_data: dict[str, JsonValue],
        timeout_seconds: int = DEFAULT_SKILL_TIMEOUT_SECONDS,
    ) -> SkillExecutionResult:
        installation = self._manager.get(skill_id, version)
        if installation is None:
            raise SkillExecutionError(
                f"skill is not installed: {skill_id}@{version}"
            )
        if not installation.enabled:
            raise SkillExecutionError(
                f"skill is disabled: {skill_id}@{version}"
            )

        try:
            package = self._manager.load_package(skill_id, version)
        except SkillInstallationError as exc:
            raise SkillExecutionError(str(exc)) from exc

        manifest = package.manifest
        if manifest.execution != "python_subprocess_v1":
            raise SkillExecutionError(
                f"skill is not executable: {skill_id}@{version}"
            )
        if manifest.entrypoint is None:
            raise SkillExecutionError(
                f"skill has no executable entrypoint: {skill_id}@{version}"
            )

        result = self._executor.execute(
            skill_id=skill_id,
            version=version,
            package_root=Path(package.root),
            entrypoint=manifest.entrypoint,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
        )
        audit = self._audit.record(
            installation_id=installation.id,
            result=result,
        )
        return result.model_copy(update={"audit_id": audit.id})
