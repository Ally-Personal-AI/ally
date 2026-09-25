"""Inspect and verify a macOS Ally update candidate without installing it.

This tool deliberately performs no network fetch and no application replacement.
It exists to make candidate acceptance a separate, testable trust boundary before
an updater is allowed to download or execute code.
"""

from __future__ import annotations

import argparse
import json
import platform
import plistlib
import re
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import macos_app_bundle
from ally.release.update_trust import (
    ReleaseMetadata,
    UpdateDecision,
    UpdateTrustError,
    compare_release_metadata,
    parse_codesign_identity,
    require_signing_identity,
)

_CODESIGN = Path("/usr/bin/codesign")
_XCRUN = Path("/usr/bin/xcrun")
_SPCTL = Path("/usr/sbin/spctl")


class PlatformTrustError(UpdateTrustError):
    """Raised when macOS rejects the signed/notarized application identity."""


def _short_version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if match is None:
        raise UpdateTrustError("bundle short version is invalid")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def inspect_release(app: Path) -> ReleaseMetadata:
    root = app.expanduser().resolve(strict=True)
    manifest = macos_app_bundle.inspect(root)
    info_path = root / "Contents/Info.plist"
    try:
        with info_path.open("rb") as handle:
            info_value: object = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise UpdateTrustError("bundle metadata is unavailable") from exc
    if not isinstance(info_value, dict):
        raise UpdateTrustError("bundle metadata is invalid")
    info = cast(dict[object, object], info_value)

    short_value = info.get("CFBundleShortVersionString")
    if not isinstance(short_value, str):
        raise UpdateTrustError("bundle short version is invalid")

    def require_string(key: str) -> str:
        value = manifest.get(key)
        if not isinstance(value, str) or not value:
            raise UpdateTrustError(f"release metadata is invalid: {key}")
        return value

    def require_int(key: str) -> int:
        value = manifest.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise UpdateTrustError(f"release metadata is invalid: {key}")
        return value

    revision_value = manifest.get("source_revision")
    revision = revision_value if isinstance(revision_value, str) else None
    return ReleaseMetadata(
        bundle_identifier=require_string("bundle_identifier"),
        ally_version=require_string("ally_version"),
        short_version=_short_version_tuple(short_value),
        build_version=require_int("build_version"),
        bridge_protocol_version=require_int("bridge_protocol_version"),
        database_schema_version=require_int("database_schema_version"),
        source_revision=revision,
    )


def compare_apps(current: Path, candidate: Path) -> UpdateDecision:
    current_root = current.expanduser().resolve(strict=True)
    candidate_root = candidate.expanduser().resolve(strict=True)
    if current_root == candidate_root:
        raise UpdateTrustError("candidate must be staged separately from the installed app")
    if current_root in candidate_root.parents or candidate_root in current_root.parents:
        raise UpdateTrustError("candidate and installed app may not be nested")
    expected = str(macos_app_bundle.release_contract()["bundle_identifier"])
    return compare_release_metadata(
        inspect_release(current_root),
        inspect_release(candidate_root),
        expected_bundle_identifier=expected,
    )


def _run_checked(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise PlatformTrustError("required macOS trust tool is unavailable") from exc
    if result.returncode != 0:
        raise PlatformTrustError("macOS release trust verification failed")
    return result


def verify_platform_trust(
    app: Path,
    *,
    expected_team_identifier: str,
) -> None:
    if platform.system() != "Darwin":
        raise PlatformTrustError("production update trust verification requires macOS")
    root = app.expanduser().resolve(strict=True)
    expected_bundle = str(macos_app_bundle.release_contract()["bundle_identifier"])
    macos_app_bundle.inspect(root)

    _run_checked([
        str(_CODESIGN),
        "--verify",
        "--deep",
        "--strict",
        "--verbose=2",
        str(root),
    ])
    details = _run_checked([
        str(_CODESIGN),
        "-dv",
        "--verbose=4",
        str(root),
    ])
    identity = parse_codesign_identity(details.stdout + "\n" + details.stderr)
    require_signing_identity(
        identity,
        expected_bundle_identifier=expected_bundle,
        expected_team_identifier=expected_team_identifier,
    )
    _run_checked([str(_XCRUN), "stapler", "validate", str(root)])
    _run_checked([
        str(_SPCTL),
        "--assess",
        "--type",
        "execute",
        "--verbose=4",
        str(root),
    ])


def verify_update(
    current: Path,
    candidate: Path,
    *,
    expected_team_identifier: str,
) -> UpdateDecision:
    decision = compare_apps(current, candidate)
    verify_platform_trust(current, expected_team_identifier=expected_team_identifier)
    verify_platform_trust(candidate, expected_team_identifier=expected_team_identifier)
    return decision


def _render(decision: UpdateDecision) -> str:
    payload: dict[str, Any] = asdict(decision)
    payload["status"] = "accepted"
    return json.dumps(payload, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or verify an Ally.app update candidate without installing it."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser(
        "compare",
        help="Run structural/provenance comparison only; not production signature trust.",
    )
    compare_parser.add_argument("--current", type=Path, required=True)
    compare_parser.add_argument("--candidate", type=Path, required=True)

    verify_parser = subparsers.add_parser(
        "verify-update",
        help="Require macOS signature, Developer ID team, notarization, and forward-only metadata.",
    )
    verify_parser.add_argument("--current", type=Path, required=True)
    verify_parser.add_argument("--candidate", type=Path, required=True)
    verify_parser.add_argument("--team-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "compare":
            decision = compare_apps(args.current, args.candidate)
        else:
            decision = verify_update(
                args.current,
                args.candidate,
                expected_team_identifier=args.team_id,
            )
        print(_render(decision))
        return 0
    except (UpdateTrustError, macos_app_bundle.BundleError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
