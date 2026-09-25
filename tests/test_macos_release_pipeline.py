from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "macos_release_pipeline.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "build", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_pipeline_rejects_invalid_source_revision(tmp_path: Path) -> None:
    result = _run(
        "--mode",
        "adhoc",
        "--source-revision",
        "not-a-commit",
        "--build-version",
        "1",
        "--output-dir",
        str(tmp_path / "release"),
    )

    assert result.returncode != 0
    assert "40-character git commit sha" in result.stderr.lower()


def test_release_pipeline_rejects_invalid_build_version(tmp_path: Path) -> None:
    result = _run(
        "--mode",
        "adhoc",
        "--source-revision",
        "a" * 40,
        "--build-version",
        "0",
        "--output-dir",
        str(tmp_path / "release"),
    )

    assert result.returncode != 0
    assert "positive integer" in result.stderr.lower()


def test_production_pipeline_requires_all_release_authorities(
    tmp_path: Path,
) -> None:
    result = _run(
        "--mode",
        "production",
        "--source-revision",
        "a" * 40,
        "--build-version",
        "1",
        "--output-dir",
        str(tmp_path / "release"),
    )

    assert result.returncode != 0
    assert "production builds require" in result.stderr.lower()


def test_adhoc_pipeline_rejects_production_credentials(tmp_path: Path) -> None:
    result = _run(
        "--mode",
        "adhoc",
        "--source-revision",
        "a" * 40,
        "--build-version",
        "1",
        "--output-dir",
        str(tmp_path / "release"),
        "--identity",
        "Developer ID Application: Synthetic",
    )

    assert result.returncode != 0
    assert "must not accept production" in result.stderr.lower()


def test_production_pipeline_never_accepts_clean_replacement(tmp_path: Path) -> None:
    result = _run(
        "--mode",
        "production",
        "--source-revision",
        "a" * 40,
        "--build-version",
        "1",
        "--output-dir",
        str(tmp_path / "release"),
        "--identity",
        "Developer ID Application: Synthetic",
        "--notary-profile",
        "synthetic-profile",
        "--release-readiness",
        str(tmp_path / "readiness.json"),
        "--validation-session",
        str(tmp_path / "session.json"),
        "--machine-acceptance",
        str(tmp_path / "machine.json"),
        "--clean",
    )

    assert result.returncode != 0
    assert "never replace" in result.stderr.lower()
