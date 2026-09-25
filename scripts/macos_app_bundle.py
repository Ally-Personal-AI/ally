"""Assemble and verify the minimal Ally macOS release bundle.

This script deliberately does not build the standalone Python helper. It accepts
an already-built executable helper, embeds it at the release-only path consumed
by Swift, and creates the signed release manifest that pins its exact bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Any, cast

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_RELEASE_BUNDLE_SWIFT = (
    _REPOSITORY_ROOT
    / "desktop/macos/Sources/AllyDesktopCore/ReleaseBundle.swift"
)
_BRIDGE_CLIENT_SWIFT = (
    _REPOSITORY_ROOT
    / "desktop/macos/Sources/AllyDesktopCore/BridgeClient.swift"
)
_PYPROJECT = _REPOSITORY_ROOT / "pyproject.toml"
_SCHEMA_PY = _REPOSITORY_ROOT / "src/ally/storage/sqlite/schema.py"

_APP_EXECUTABLE_NAME = "AllyDesktop"
_DISPLAY_NAME = "Ally"
_MANIFEST_SCHEMA_VERSION = 2


class BundleError(RuntimeError):
    """Raised when an app bundle cannot be assembled or verified safely."""


def _single_swift_string(path: Path, name: str) -> str:
    content = path.read_text(encoding="utf-8")
    match = re.search(
        rf"\b{name}\s*=\s*\"([^\"]+)\"",
        content,
    )
    if match is None:
        raise BundleError(f"could not read Swift release constant: {name}")
    return match.group(1)


def _single_swift_integer(path: Path, name: str) -> int:
    content = path.read_text(encoding="utf-8")
    match = re.search(rf"\b{name}\s*=\s*(\d+)", content)
    if match is None:
        raise BundleError(f"could not read Swift protocol constant: {name}")
    return int(match.group(1))


def _single_python_integer(path: Path, name: str) -> int:
    content = path.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{name}\s*=\s*(\d+)\s*$", content, re.MULTILINE)
    if match is None:
        raise BundleError(f"could not read Python release constant: {name}")
    return int(match.group(1))


def release_contract() -> dict[str, str | int]:
    return {
        "bundle_identifier": _single_swift_string(
            _RELEASE_BUNDLE_SWIFT,
            "bundleIdentifier",
        ),
        "helper_relative_path": _single_swift_string(
            _RELEASE_BUNDLE_SWIFT,
            "helperRelativePath",
        ),
        "manifest_relative_path": _single_swift_string(
            _RELEASE_BUNDLE_SWIFT,
            "manifestRelativePath",
        ),
        "bridge_protocol_version": _single_swift_integer(
            _BRIDGE_CLIENT_SWIFT,
            "supportedProtocolVersion",
        ),
        "database_schema_version": _single_python_integer(
            _SCHEMA_PY,
            "CURRENT_SCHEMA_VERSION",
        ),
    }


def ally_version() -> str:
    with _PYPROJECT.open("rb") as handle:
        document = cast(dict[str, object], tomllib.load(handle))
    project_value = document.get("project")
    if not isinstance(project_value, dict):
        raise BundleError("pyproject project metadata is missing")
    project = cast(dict[str, object], project_value)
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise BundleError("pyproject project version is missing")
    return version


def short_version(version: str) -> str:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise BundleError("Ally version does not begin with semantic version numbers")
    return ".".join(match.groups())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_executable(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise BundleError(f"{label} must be a regular file")
    if not os.access(resolved, os.X_OK):
        raise BundleError(f"{label} must be executable")
    return resolved


def _write_info_plist(
    destination: Path,
    *,
    bundle_identifier: str,
    version: str,
    build_version: str,
) -> None:
    payload: dict[str, Any] = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": _DISPLAY_NAME,
        "CFBundleExecutable": _APP_EXECUTABLE_NAME,
        "CFBundleIdentifier": bundle_identifier,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": _DISPLAY_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": short_version(version),
        "CFBundleVersion": build_version,
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
    }
    with destination.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)


def assemble(
    *,
    app_executable: Path,
    helper: Path,
    output: Path,
    source_revision: str | None,
    build_version: str,
    replace: bool,
) -> Path:
    app_source = _require_executable(app_executable, "app executable")
    helper_source = _require_executable(helper, "desktop helper")
    if not re.fullmatch(r"[1-9]\d*", build_version):
        raise BundleError("build version must be a positive integer")
    if source_revision is not None and not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise BundleError(
            "source revision must be a full lowercase 40-character Git commit SHA"
        )

    contract = release_contract()
    bundle_identifier = str(contract["bundle_identifier"])
    helper_relative_path = str(contract["helper_relative_path"])
    manifest_relative_path = str(contract["manifest_relative_path"])
    protocol_version = int(contract["bridge_protocol_version"])
    database_schema_version = int(contract["database_schema_version"])
    version = ally_version()

    destination = output.expanduser().resolve()
    if destination.suffix != ".app":
        raise BundleError("output must be an .app bundle path")
    if destination.exists() and not replace:
        raise BundleError("output bundle already exists; pass --replace to replace it")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    ) as temporary:
        staging = Path(temporary) / destination.name
        contents = staging / "Contents"
        macos = contents / "MacOS"
        resources = contents / "Resources"
        helper_destination = staging / helper_relative_path
        manifest_destination = staging / manifest_relative_path

        macos.mkdir(parents=True)
        resources.mkdir(parents=True)
        helper_destination.parent.mkdir(parents=True, exist_ok=True)
        manifest_destination.parent.mkdir(parents=True, exist_ok=True)

        app_destination = macos / _APP_EXECUTABLE_NAME
        shutil.copy2(app_source, app_destination)
        shutil.copy2(helper_source, helper_destination)
        app_destination.chmod(
            app_destination.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )
        helper_destination.chmod(
            helper_destination.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )

        _write_info_plist(
            contents / "Info.plist",
            bundle_identifier=bundle_identifier,
            version=version,
            build_version=build_version,
        )
        manifest = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "bundle_identifier": bundle_identifier,
            "ally_version": version,
            "build_version": int(build_version),
            "bridge_protocol_version": protocol_version,
            "database_schema_version": database_schema_version,
            "helper_relative_path": helper_relative_path,
            "helper_sha256": sha256(helper_destination),
            "source_revision": source_revision,
        }
        manifest_destination.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        verify(staging)

        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)

    return destination


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"invalid release manifest: {path}") from exc
    if not isinstance(value, dict):
        raise BundleError("release manifest must be a JSON object")
    return cast(dict[str, Any], value)


def inspect(app: Path) -> dict[str, Any]:
    """Validate self-contained bundle metadata without tying it to this checkout."""

    root = app.expanduser().resolve(strict=True)
    if not root.is_dir() or root.suffix != ".app":
        raise BundleError("bundle must be an existing .app directory")

    contract = release_contract()
    bundle_identifier = str(contract["bundle_identifier"])
    helper_relative_path = str(contract["helper_relative_path"])
    manifest_relative_path = str(contract["manifest_relative_path"])

    info_path = root / "Contents/Info.plist"
    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise BundleError("Info.plist is missing or invalid") from exc

    if info.get("CFBundleIdentifier") != bundle_identifier:
        raise BundleError("bundle identifier does not match the release contract")
    if info.get("CFBundleExecutable") != _APP_EXECUTABLE_NAME:
        raise BundleError("bundle executable does not match the release contract")

    app_executable = root / "Contents/MacOS" / _APP_EXECUTABLE_NAME
    helper = root / helper_relative_path
    manifest_path = root / manifest_relative_path
    for path, label in (
        (app_executable, "app executable"),
        (helper, "desktop helper"),
    ):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise BundleError(f"{label} is missing or not executable")

    manifest = _load_json_object(manifest_path)
    expected = {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "bundle_identifier": bundle_identifier,
        "helper_relative_path": helper_relative_path,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise BundleError(f"release manifest mismatch: {key}")

    ally_manifest_version = manifest.get("ally_version")
    if not isinstance(ally_manifest_version, str) or not ally_manifest_version:
        raise BundleError("release manifest Ally version is invalid")
    bridge_protocol = manifest.get("bridge_protocol_version")
    if not isinstance(bridge_protocol, int) or isinstance(bridge_protocol, bool) or bridge_protocol < 1:
        raise BundleError("release manifest bridge protocol version is invalid")
    database_schema = manifest.get("database_schema_version")
    if not isinstance(database_schema, int) or isinstance(database_schema, bool) or database_schema < 0:
        raise BundleError("release manifest database schema version is invalid")
    build_manifest = manifest.get("build_version")
    if not isinstance(build_manifest, int) or isinstance(build_manifest, bool) or build_manifest < 1:
        raise BundleError("release manifest build version is invalid")

    info_build = info.get("CFBundleVersion")
    if not isinstance(info_build, str) or not re.fullmatch(r"[1-9]\d*", info_build):
        raise BundleError("bundle build version is invalid")
    if int(info_build) != build_manifest:
        raise BundleError("bundle build version does not match release manifest")
    info_short_version = info.get("CFBundleShortVersionString")
    if not isinstance(info_short_version, str) or not re.fullmatch(
        r"\d+\.\d+\.\d+",
        info_short_version,
    ):
        raise BundleError("bundle short version is invalid")
    if short_version(ally_manifest_version) != info_short_version:
        raise BundleError("bundle short version does not match release manifest")

    source_revision = manifest.get("source_revision")
    if source_revision is not None and (
        not isinstance(source_revision, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None
    ):
        raise BundleError("release manifest source revision is invalid")
    helper_digest = manifest.get("helper_sha256")
    if not isinstance(helper_digest, str) or re.fullmatch(r"[0-9a-f]{64}", helper_digest) is None:
        raise BundleError("release manifest helper hash is invalid")
    if helper_digest != sha256(helper):
        raise BundleError("desktop helper hash does not match release manifest")

    forbidden_names = {".ally", "backups", "data", "models", "secrets"}
    embedded_forbidden = [
        path
        for path in root.rglob("*")
        if path.name in forbidden_names
    ]
    if embedded_forbidden:
        raise BundleError("release bundle contains a user-data/runtime directory")

    return manifest


def verify(app: Path) -> dict[str, Any]:
    """Verify a bundle built from the current checkout's exact release contract."""

    manifest = inspect(app)
    contract = release_contract()
    expected = {
        "ally_version": ally_version(),
        "bridge_protocol_version": int(contract["bridge_protocol_version"]),
        "database_schema_version": int(contract["database_schema_version"]),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise BundleError(f"release manifest mismatch: {key}")
    return manifest


def refresh_helper_hash(app: Path) -> str:
    """Refresh the manifest after signing the embedded helper, before app signing."""

    root = app.expanduser().resolve(strict=True)
    contract = release_contract()
    manifest_path = root / str(contract["manifest_relative_path"])
    helper = root / str(contract["helper_relative_path"])
    if not helper.is_file() or not os.access(helper, os.X_OK):
        raise BundleError("desktop helper is missing or not executable")

    manifest = _load_json_object(manifest_path)
    expected_identity = str(contract["bundle_identifier"])
    if (
        manifest.get("schema_version") != _MANIFEST_SCHEMA_VERSION
        or manifest.get("bundle_identifier") != expected_identity
        or manifest.get("ally_version") != ally_version()
        or manifest.get("bridge_protocol_version")
        != int(contract["bridge_protocol_version"])
        or manifest.get("database_schema_version")
        != int(contract["database_schema_version"])
        or not isinstance(manifest.get("build_version"), int)
        or isinstance(manifest.get("build_version"), bool)
        or int(manifest["build_version"]) < 1
        or (
            manifest.get("source_revision") is not None
            and (
                not isinstance(manifest.get("source_revision"), str)
                or re.fullmatch(r"[0-9a-f]{40}", str(manifest["source_revision"])) is None
            )
        )
        or manifest.get("helper_relative_path")
        != str(contract["helper_relative_path"])
    ):
        raise BundleError("release manifest contract cannot be refreshed safely")

    digest = sha256(helper)
    manifest["helper_sha256"] = digest
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble or verify the Ally macOS application bundle."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--app-executable", type=Path, required=True)
    assemble_parser.add_argument("--helper", type=Path, required=True)
    assemble_parser.add_argument("--output", type=Path, required=True)
    assemble_parser.add_argument("--source-revision")
    assemble_parser.add_argument("--build-version", default="1")
    assemble_parser.add_argument("--replace", action="store_true")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("app", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "assemble":
            built = assemble(
                app_executable=args.app_executable,
                helper=args.helper,
                output=args.output,
                source_revision=args.source_revision,
                build_version=args.build_version,
                replace=args.replace,
            )
            print(built)
            return 0

        manifest = verify(args.app)
        print(json.dumps(manifest, sort_keys=True))
        return 0
    except (BundleError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
