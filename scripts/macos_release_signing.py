"""Sign, verify, and notarize an assembled Ally macOS application bundle.

Notarization authentication is intentionally limited to an existing notarytool
Keychain profile. Apple IDs, passwords, private keys, and API secrets are never
accepted as command-line arguments by this script.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

import macos_app_bundle

_HELPER_RELATIVE_PATH = Path("Contents/Helpers/ally-desktop-bridge")


class SigningError(RuntimeError):
    """Raised when release signing/notarization prerequisites are invalid."""


def _require_macos(*, dry_run: bool) -> None:
    if sys.platform != "darwin" and not dry_run:
        raise SigningError("macOS signing and notarization require macOS")


def _run(command: Sequence[str], *, dry_run: bool) -> None:
    if dry_run:
        print(shlex.join(command))
        return
    subprocess.run(command, check=True)


def sign(
    app: Path,
    *,
    identity: str,
    timestamp: bool,
    dry_run: bool,
) -> None:
    _require_macos(dry_run=dry_run)
    root = app.expanduser().resolve(strict=True)
    macos_app_bundle.verify(root)
    if not identity.strip():
        raise SigningError("signing identity cannot be empty")
    if identity == "-" and timestamp:
        raise SigningError("ad-hoc signing cannot request a trusted timestamp")

    timestamp_args = ["--timestamp"] if timestamp else []
    helper = root / _HELPER_RELATIVE_PATH

    _run(
        [
            "codesign",
            "--force",
            "--options",
            "runtime",
            *timestamp_args,
            "--sign",
            identity,
            str(helper),
        ],
        dry_run=dry_run,
    )
    if not dry_run:
        macos_app_bundle.refresh_helper_hash(root)
        macos_app_bundle.verify(root)
    _run(
        [
            "codesign",
            "--force",
            "--options",
            "runtime",
            *timestamp_args,
            "--sign",
            identity,
            str(root),
        ],
        dry_run=dry_run,
    )
    verify_signature(root, dry_run=dry_run)


def verify_signature(app: Path, *, dry_run: bool) -> None:
    _require_macos(dry_run=dry_run)
    root = app.expanduser().resolve(strict=True)
    _run(
        [
            "codesign",
            "--verify",
            "--deep",
            "--strict",
            "--verbose=2",
            str(root),
        ],
        dry_run=dry_run,
    )


def notarize(
    app: Path,
    *,
    keychain_profile: str,
    dry_run: bool,
) -> None:
    _require_macos(dry_run=dry_run)
    root = app.expanduser().resolve(strict=True)
    macos_app_bundle.verify(root)
    if not keychain_profile.strip():
        raise SigningError("notarytool Keychain profile cannot be empty")

    verify_signature(root, dry_run=dry_run)
    with tempfile.TemporaryDirectory(prefix="ally-notarize-") as temporary:
        archive = Path(temporary) / "Ally.zip"
        _run(
            [
                "ditto",
                "-c",
                "-k",
                "--keepParent",
                str(root),
                str(archive),
            ],
            dry_run=dry_run,
        )
        _run(
            [
                "xcrun",
                "notarytool",
                "submit",
                str(archive),
                "--keychain-profile",
                keychain_profile,
                "--wait",
            ],
            dry_run=dry_run,
        )

    _run(
        ["xcrun", "stapler", "staple", str(root)],
        dry_run=dry_run,
    )
    _run(
        ["xcrun", "stapler", "validate", str(root)],
        dry_run=dry_run,
    )
    _run(
        [
            "spctl",
            "--assess",
            "--type",
            "execute",
            "--verbose=4",
            str(root),
        ],
        dry_run=dry_run,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sign, verify, or notarize an assembled Ally.app bundle."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sign_parser = subparsers.add_parser("sign")
    sign_parser.add_argument("app", type=Path)
    sign_parser.add_argument("--identity", required=True)
    sign_parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="Disable trusted timestamps, intended only for local ad-hoc validation.",
    )
    sign_parser.add_argument("--dry-run", action="store_true")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("app", type=Path)
    verify_parser.add_argument("--dry-run", action="store_true")

    notarize_parser = subparsers.add_parser("notarize")
    notarize_parser.add_argument("app", type=Path)
    notarize_parser.add_argument("--keychain-profile", required=True)
    notarize_parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "sign":
            sign(
                args.app,
                identity=args.identity,
                timestamp=not args.no_timestamp,
                dry_run=args.dry_run,
            )
        elif args.command == "verify":
            verify_signature(args.app, dry_run=args.dry_run)
        else:
            notarize(
                args.app,
                keychain_profile=args.keychain_profile,
                dry_run=args.dry_run,
            )
        return 0
    except (
        SigningError,
        macos_app_bundle.BundleError,
        FileNotFoundError,
        subprocess.CalledProcessError,
    ) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
