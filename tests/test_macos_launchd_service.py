from __future__ import annotations

import json
import os
import plistlib
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from ally.cli import main
from ally.service.macos_launchd import (
    LAUNCHD_INTERVAL_SECONDS,
    LAUNCHD_LABEL,
    LaunchctlResult,
    MacOSLaunchdService,
    ManagedServiceError,
    ManagedServicePaths,
)


class FakeLaunchctl:
    def __init__(self, *, bootstrap_succeeds: bool = True) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.loaded = False
        self.running = False
        self.bootstrap_succeeds = bootstrap_succeeds

    def run(self, arguments: Sequence[str]) -> LaunchctlResult:
        call = tuple(arguments)
        self.calls.append(call)
        action = call[0]
        if action == "print":
            if not self.loaded:
                return LaunchctlResult(113)
            state = "running" if self.running else "waiting"
            return LaunchctlResult(0, f"state = {state}\n")
        if action == "bootstrap":
            if not self.bootstrap_succeeds:
                return LaunchctlResult(5)
            self.loaded = True
            self.running = True
            return LaunchctlResult(0)
        if action == "kickstart":
            self.running = True
            return LaunchctlResult(0)
        if action == "bootout":
            self.loaded = False
            self.running = False
            return LaunchctlResult(0)
        raise AssertionError(f"unexpected launchctl call: {call}")


def build_service(
    root: Path,
    *,
    runner: FakeLaunchctl | None = None,
    supported: bool = True,
) -> tuple[MacOSLaunchdService, FakeLaunchctl]:
    launchctl = runner or FakeLaunchctl()
    paths = ManagedServicePaths(
        plist=root / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist",
        stdout_log=root / "data" / "service" / "logs" / "stdout.log",
        stderr_log=root / "data" / "service" / "logs" / "stderr.log",
    )
    service = MacOSLaunchdService(
        paths=paths,
        runner=launchctl,
        executable=Path(sys.executable),
        uid=501,
        supported=supported,
    )
    return service, launchctl


def test_definition_is_deterministic_and_invokes_one_bounded_cycle(tmp_path: Path) -> None:
    service, _ = build_service(tmp_path)

    first = service.definition_bytes()
    second = service.definition_bytes()
    definition = plistlib.loads(first)

    assert first == second
    assert definition["Label"] == LAUNCHD_LABEL
    assert definition["ProgramArguments"] == [
        str(Path(sys.executable).resolve()),
        "-m",
        "ally.cli",
        "service",
        "cycle",
        "--json",
    ]
    assert definition["StartInterval"] == LAUNCHD_INTERVAL_SECONDS
    assert definition["RunAtLoad"] is True
    assert Path(definition["StandardOutPath"]).is_absolute()
    assert Path(definition["StandardErrorPath"]).is_absolute()


def test_unsupported_status_is_read_only(tmp_path: Path) -> None:
    service, runner = build_service(tmp_path, supported=False)

    status = service.status()

    assert not status.supported
    assert not status.configured
    assert runner.calls == []


@pytest.mark.parametrize("action", ["install", "start", "stop", "uninstall", "retire_legacy"])
def test_mutations_are_rejected_off_macos(tmp_path: Path, action: str) -> None:
    service, runner = build_service(tmp_path, supported=False)

    with pytest.raises(ManagedServiceError, match="only on macOS"):
        getattr(service, action)()

    assert runner.calls == []


def test_install_start_stop_and_uninstall_lifecycle(tmp_path: Path) -> None:
    service, runner = build_service(tmp_path)

    installed = service.install()
    assert installed.configured
    assert installed.definition_matches
    assert installed.loaded
    assert installed.running
    assert service.paths.plist.stat().st_mode & 0o777 == 0o600
    assert ("bootstrap", "gui/501", str(service.paths.plist.resolve())) in runner.calls

    service.stop()
    assert not service.status().running
    calls_before_start = len(runner.calls)
    service.start()
    assert service.status().running
    start_calls = runner.calls[calls_before_start:]
    assert any(call[0] == "bootstrap" for call in start_calls)
    assert not any(call[0] == "kickstart" for call in start_calls)

    removed = service.uninstall()
    assert not removed.configured
    assert not removed.loaded
    assert not service.paths.plist.exists()


def test_start_kickstarts_an_already_loaded_agent(tmp_path: Path) -> None:
    service, runner = build_service(tmp_path)
    service.install()
    runner.running = False
    calls_before_start = len(runner.calls)

    service.start()

    assert ("kickstart", "-k", service.service_target) in runner.calls[calls_before_start:]


def test_install_is_idempotent_for_the_exact_definition(tmp_path: Path) -> None:
    service, runner = build_service(tmp_path)
    service.install()
    before = service.paths.plist.read_bytes()
    calls_before = len(runner.calls)

    status = service.install()

    assert status.loaded
    assert service.paths.plist.read_bytes() == before
    assert not any(call[0] == "bootstrap" for call in runner.calls[calls_before:])


def test_install_refuses_an_existing_different_definition(tmp_path: Path) -> None:
    service, runner = build_service(tmp_path)
    service.paths.plist.parent.mkdir(parents=True)
    service.paths.plist.write_text("not Ally's definition", encoding="utf-8")

    with pytest.raises(ManagedServiceError, match="differs"):
        service.install()

    assert service.paths.plist.read_text(encoding="utf-8") == "not Ally's definition"
    assert runner.calls == []


def test_install_refuses_a_definition_symlink(tmp_path: Path) -> None:
    service, runner = build_service(tmp_path)
    target = tmp_path / "target.plist"
    target.write_bytes(service.definition_bytes())
    service.paths.plist.parent.mkdir(parents=True)
    service.paths.plist.symlink_to(target)

    with pytest.raises(ManagedServiceError, match="differs"):
        service.install()

    assert service.paths.plist.is_symlink()
    assert runner.calls == []


def test_failed_bootstrap_removes_only_the_new_definition(tmp_path: Path) -> None:
    service, _ = build_service(
        tmp_path,
        runner=FakeLaunchctl(bootstrap_succeeds=False),
    )

    with pytest.raises(ManagedServiceError, match="could not load"):
        service.install()

    assert not service.paths.plist.exists()


def test_atomic_publication_refuses_a_racing_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = build_service(tmp_path)
    service.paths.plist.parent.mkdir(parents=True)
    service.paths.stdout_log.parent.mkdir(parents=True)
    original_link = os.link

    def racing_link(source: Path, destination: Path) -> None:
        Path(destination).write_text("competitor", encoding="utf-8")
        original_link(source, destination)

    monkeypatch.setattr(os, "link", racing_link)

    with pytest.raises(ManagedServiceError, match="appeared during installation"):
        service.install()

    assert service.paths.plist.read_text(encoding="utf-8") == "competitor"


def test_cli_can_inspect_definition_without_macos(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["service", "managed", "inspect"]) == 0

    definition = plistlib.loads(capsys.readouterr().out.encode())
    assert definition["Label"] == LAUNCHD_LABEL


def test_cli_status_has_stable_json_shape(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["service", "managed", "status", "--json"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["label"] == LAUNCHD_LABEL
    assert result["supported"] is (sys.platform == "darwin")
    assert set(result) == {
        "configured",
        "definition_matches",
        "label",
        "loaded",
        "plist_path",
        "running",
        "supported",
    }


def test_migration_recognizes_historical_executable_path(tmp_path: Path) -> None:
    service, runner = build_service(tmp_path)
    definition = service.definition()
    arguments = list(definition["ProgramArguments"])
    arguments[0] = "/Applications/SyntheticOldAlly/bin/python"
    definition["ProgramArguments"] = arguments
    service.paths.plist.parent.mkdir(parents=True)
    service.paths.plist.write_bytes(
        plistlib.dumps(definition, fmt=plistlib.FMT_XML, sort_keys=True)
    )

    status = service.migration_status()

    assert status.configured
    assert status.definition_state == "recognized_legacy"
    assert status.can_retire
    assert not status.loaded
    assert runner.calls[-1] == ("print", service.service_target)


def test_migration_refuses_modified_or_symlinked_definition(tmp_path: Path) -> None:
    service, _ = build_service(tmp_path)
    definition = service.definition()
    definition["StartInterval"] = 30
    service.paths.plist.parent.mkdir(parents=True)
    service.paths.plist.write_bytes(
        plistlib.dumps(definition, fmt=plistlib.FMT_XML, sort_keys=True)
    )

    status = service.migration_status()

    assert status.definition_state == "modified"
    assert not status.can_retire
    with pytest.raises(ManagedServiceError, match="not recognized"):
        service.retire_legacy()
    assert service.paths.plist.exists()

    target = tmp_path / "recognized.plist"
    target.write_bytes(service.definition_bytes())
    service.paths.plist.unlink()
    service.paths.plist.symlink_to(target)

    symlink_status = service.migration_status()

    assert symlink_status.definition_state == "modified"
    assert not symlink_status.can_retire
    with pytest.raises(ManagedServiceError, match="not recognized"):
        service.retire_legacy()
    assert service.paths.plist.is_symlink()


def test_retire_legacy_unloads_then_removes_recognized_definition(
    tmp_path: Path,
) -> None:
    service, runner = build_service(tmp_path)
    definition = service.definition()
    arguments = list(definition["ProgramArguments"])
    arguments[0] = "/Applications/SyntheticOldAlly/bin/python"
    definition["ProgramArguments"] = arguments
    service.paths.plist.parent.mkdir(parents=True)
    service.paths.plist.write_bytes(
        plistlib.dumps(definition, fmt=plistlib.FMT_XML, sort_keys=True)
    )
    runner.loaded = True
    runner.running = True

    status = service.retire_legacy()

    assert not status.configured
    assert status.definition_state == "absent"
    assert not status.loaded
    assert not status.running
    assert not service.paths.plist.exists()
    assert ("bootout", service.service_target) in runner.calls
