from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

BUNDLE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "macos_app_bundle.py"
SIGNING_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "macos_release_signing.py"
)


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _bundle(tmp_path: Path) -> Path:
    app_binary = _executable(tmp_path / "app-binary")
    helper = _executable(tmp_path / "helper-binary")
    app = tmp_path / "Ally.app"
    subprocess.run(
        [
            sys.executable,
            str(BUNDLE_SCRIPT),
            "assemble",
            "--app-executable",
            str(app_binary),
            "--helper",
            str(helper),
            "--output",
            str(app),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return app


def test_sign_dry_run_signs_helper_before_outer_bundle(tmp_path: Path) -> None:
    app = _bundle(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SIGNING_SCRIPT),
            "sign",
            str(app),
            "--identity",
            "Developer ID Application: Synthetic",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 3
    assert "Contents/Helpers/ally-desktop-bridge" in lines[0]
    assert "--timestamp" in lines[0]
    assert str(app) in lines[1]
    assert "--timestamp" in lines[1]
    assert "codesign --verify" in lines[2]


def test_ad_hoc_signing_requires_explicit_no_timestamp(tmp_path: Path) -> None:
    app = _bundle(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SIGNING_SCRIPT),
            "sign",
            str(app),
            "--identity",
            "-",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "ad-hoc signing" in result.stderr.lower()


def test_notarize_uses_keychain_profile_without_secret_arguments(
    tmp_path: Path,
) -> None:
    app = _bundle(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SIGNING_SCRIPT),
            "notarize",
            str(app),
            "--keychain-profile",
            "synthetic-notary-profile",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    rendered = result.stdout
    assert "notarytool submit" in rendered
    assert "--keychain-profile synthetic-notary-profile" in rendered
    assert "stapler staple" in rendered
    assert "spctl --assess" in rendered
    for forbidden in ("--apple-id", "--password", "--key-id", "--issuer"):
        assert forbidden not in rendered


def test_notarization_parser_does_not_accept_password_credentials(
    tmp_path: Path,
) -> None:
    app = _bundle(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SIGNING_SCRIPT),
            "notarize",
            str(app),
            "--keychain-profile",
            "synthetic-notary-profile",
            "--password",
            "must-not-be-accepted",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr.lower()
