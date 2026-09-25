from __future__ import annotations

import json
import plistlib
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "macos_app_bundle.py"


def _executable(path: Path, contents: str) -> Path:
    path.write_text(contents, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _assemble(tmp_path: Path) -> Path:
    app_executable = _executable(
        tmp_path / "AllyDesktop",
        "#!/bin/sh\necho synthetic-app\n",
    )
    helper = _executable(
        tmp_path / "ally-desktop-bridge",
        "#!/bin/sh\necho synthetic-helper\n",
    )
    output = tmp_path / "Ally.app"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "assemble",
            "--app-executable",
            str(app_executable),
            "--helper",
            str(helper),
            "--output",
            str(output),
            "--source-revision",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--build-version",
            "7",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def test_assemble_creates_release_contract_and_manifest(tmp_path: Path) -> None:
    app = _assemble(tmp_path)

    with (app / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleIdentifier"] == "ai.ally.personal"
    assert info["CFBundleExecutable"] == "AllyDesktop"
    assert info["CFBundleShortVersionString"] == "0.1.0"
    assert info["CFBundleVersion"] == "7"

    manifest = json.loads(
        (app / "Contents/Resources/release-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["schema_version"] == 2
    assert manifest["bundle_identifier"] == "ai.ally.personal"
    assert manifest["ally_version"] == "0.1.0.dev0"
    assert manifest["build_version"] == 7
    assert manifest["bridge_protocol_version"] == 7
    assert manifest["database_schema_version"] == 14
    assert (
        manifest["helper_relative_path"]
        == "Contents/Helpers/ally-desktop-bridge"
    )
    assert len(manifest["helper_sha256"]) == 64
    assert manifest["source_revision"] == "a" * 40

    verified = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", str(app)],
        check=True,
        capture_output=True,
        text=True,
    )
    verified_manifest = json.loads(verified.stdout)
    assert verified_manifest["helper_sha256"] == manifest["helper_sha256"]


def test_verify_rejects_tampered_helper(tmp_path: Path) -> None:
    app = _assemble(tmp_path)
    helper = app / "Contents/Helpers/ally-desktop-bridge"
    helper.write_text("#!/bin/sh\necho tampered\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", str(app)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "helper hash" in result.stderr.lower()


def test_assemble_refuses_overwrite_without_explicit_replace(
    tmp_path: Path,
) -> None:
    app = _assemble(tmp_path)
    assert app.exists()

    app_executable = _executable(
        tmp_path / "second-app",
        "#!/bin/sh\necho second-app\n",
    )
    helper = _executable(
        tmp_path / "second-helper",
        "#!/bin/sh\necho second-helper\n",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "assemble",
            "--app-executable",
            str(app_executable),
            "--helper",
            str(helper),
            "--output",
            str(app),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "already exists" in result.stderr.lower()


@pytest.mark.parametrize("build_version", ["0", "-1", "1.2", "synthetic"])
def test_assemble_rejects_invalid_build_version(
    tmp_path: Path,
    build_version: str,
) -> None:
    app_executable = _executable(tmp_path / "app", "#!/bin/sh\nexit 0\n")
    helper = _executable(tmp_path / "helper", "#!/bin/sh\nexit 0\n")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "assemble",
            "--app-executable",
            str(app_executable),
            "--helper",
            str(helper),
            "--output",
            str(tmp_path / "Ally.app"),
            "--build-version",
            build_version,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "positive integer" in result.stderr.lower()


def test_refresh_helper_hash_rebinds_signed_helper_bytes(tmp_path: Path) -> None:
    app = _assemble(tmp_path)
    helper = app / "Contents/Helpers/ally-desktop-bridge"
    helper.write_text("#!/bin/sh\necho post-sign-bytes\n", encoding="utf-8")
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)

    refreshed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(SCRIPT.parent)!r}); "
                "import macos_app_bundle; "
                f"print(macos_app_bundle.refresh_helper_hash(Path({str(app)!r})))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert len(refreshed.stdout.strip()) == 64

    verified = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", str(app)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(verified.stdout)["helper_sha256"] == refreshed.stdout.strip()


def test_assemble_rejects_non_commit_source_revision(tmp_path: Path) -> None:
    app_executable = _executable(tmp_path / "app-source", "#!/bin/sh\nexit 0\n")
    helper = _executable(tmp_path / "helper-source", "#!/bin/sh\nexit 0\n")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "assemble",
            "--app-executable",
            str(app_executable),
            "--helper",
            str(helper),
            "--output",
            str(tmp_path / "Ally.app"),
            "--source-revision",
            "not-a-full-commit",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "40-character git commit sha" in result.stderr.lower()


def test_verify_rejects_manifest_build_mismatch(tmp_path: Path) -> None:
    app = _assemble(tmp_path)
    manifest_path = app / "Contents/Resources/release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["build_version"] = 8
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", str(app)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "build version" in result.stderr.lower()
