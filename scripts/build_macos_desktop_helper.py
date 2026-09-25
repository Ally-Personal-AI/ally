"""Build and verify a self-contained macOS ally-desktop-bridge helper."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_ENTRYPOINT = _REPOSITORY_ROOT / "scripts/ally_desktop_bridge_entry.py"
_HELPER_NAME = "ally-desktop-bridge"
_BRIDGE_CLIENT_SWIFT = (
    _REPOSITORY_ROOT
    / "desktop/macos/Sources/AllyDesktopCore/BridgeClient.swift"
)
_MAXIMUM_SMOKE_RESPONSE_BYTES = 2 * 1024 * 1024


class HelperBuildError(RuntimeError):
    """Raised when the standalone helper cannot be built or verified safely."""


def _desktop_protocol_version() -> int:
    content = _BRIDGE_CLIENT_SWIFT.read_text(encoding="utf-8")
    match = re.search(r"\bsupportedProtocolVersion\s*=\s*(\d+)", content)
    if match is None:
        raise HelperBuildError("desktop protocol version could not be determined")
    return int(match.group(1))


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise HelperBuildError("standalone desktop helper builds require macOS")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _pyinstaller_version() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    version = result.stdout.strip()
    if not version:
        raise HelperBuildError("PyInstaller version could not be determined")
    return version


def build(
    *,
    output: Path,
    codesign_identity: str | None,
    clean: bool,
) -> Path:
    _require_macos()
    if not _ENTRYPOINT.is_file():
        raise HelperBuildError("desktop helper entry point is missing")

    destination = output.expanduser().resolve()
    if destination.exists() and not clean:
        raise HelperBuildError("helper output already exists; pass --clean to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)

    version = _pyinstaller_version()
    with tempfile.TemporaryDirectory(prefix="ally-helper-build-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        work = root / "work"
        spec = root / "spec"
        dist.mkdir()
        work.mkdir()
        spec.mkdir()

        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--console",
            "--clean",
            "--noconfirm",
            "--name",
            _HELPER_NAME,
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
            "--specpath",
            str(spec),
            "--collect-data",
            "ally",
        ]
        if codesign_identity is not None:
            identity = codesign_identity.strip()
            if not identity or identity == "-":
                raise HelperBuildError(
                    "real helper signing requires a non-empty Developer ID identity"
                )
            command.extend(["--codesign-identity", identity])
        command.append(str(_ENTRYPOINT))
        _run(command, cwd=_REPOSITORY_ROOT)

        built = dist / _HELPER_NAME
        if not built.is_file() or not os.access(built, os.X_OK):
            raise HelperBuildError("PyInstaller did not produce an executable helper")

        shutil.copy2(built, destination)
        destination.chmod(destination.stat().st_mode | 0o111)

    verify(destination)
    print(
        json.dumps(
            {
                "helper": str(destination),
                "pyinstaller_version": version,
                "python_version": platform.python_version(),
                "architecture": platform.machine(),
                "codesign_identity_supplied": codesign_identity is not None,
            },
            sort_keys=True,
        )
    )
    return destination


def _bridge_call(helper: Path, method: str) -> dict[str, object]:
    request = json.dumps(
        {"id": "release-smoke", "method": method, "params": {}},
        separators=(",", ":"),
    )
    environment = {
        key: value
        for key in ("HOME", "TMPDIR", "LANG", "LC_ALL")
        if (value := os.environ.get(key)) is not None
    }
    result = subprocess.run(
        [str(helper), "--once"],
        input=request + "\n",
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        cwd=Path(tempfile.gettempdir()),
    )
    if result.returncode != 0:
        raise HelperBuildError(
            f"frozen helper failed {method} smoke with exit {result.returncode}"
        )
    if len(result.stdout.encode("utf-8")) > _MAXIMUM_SMOKE_RESPONSE_BYTES:
        raise HelperBuildError("frozen helper smoke response exceeded the desktop bound")
    try:
        payload_value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HelperBuildError("frozen helper returned invalid JSON") from exc
    if not isinstance(payload_value, dict):
        raise HelperBuildError("frozen helper response must be a JSON object")
    return cast(dict[str, object], payload_value)


def verify(helper: Path) -> None:
    _require_macos()
    resolved = helper.expanduser().resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise HelperBuildError("helper is missing or not executable")

    info = _bridge_call(resolved, "bridge.info")
    if info.get("ok") is not True:
        raise HelperBuildError("frozen helper bridge.info failed")
    result_value = info.get("result")
    if not isinstance(result_value, dict):
        raise HelperBuildError("frozen helper bridge.info result is invalid")
    result = cast(dict[str, object], result_value)
    if result.get("protocol_version") != _desktop_protocol_version():
        raise HelperBuildError("frozen helper protocol version does not match desktop")

    bootstrap = _bridge_call(resolved, "bootstrap")
    if bootstrap.get("ok") is not True:
        raise HelperBuildError("frozen helper bootstrap failed outside the checkout")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify the standalone macOS Ally desktop helper."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--codesign-identity")
    build_parser.add_argument("--clean", action="store_true")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("helper", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            build(
                output=args.output,
                codesign_identity=args.codesign_identity,
                clean=args.clean,
            )
        else:
            verify(args.helper)
        return 0
    except (
        HelperBuildError,
        FileNotFoundError,
        subprocess.CalledProcessError,
    ) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
