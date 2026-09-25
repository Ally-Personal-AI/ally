from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from ally.release import (
    ReleaseIdentity,
    ReleaseMetadata,
    UpdateTrustError,
    compare_release_metadata,
    parse_codesign_identity,
    require_signing_identity,
)
from ally.storage.sqlite.schema import CURRENT_SCHEMA_VERSION, MIGRATIONS

BUNDLE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "macos_app_bundle.py"
UPDATE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "macos_update_trust.py"


def _metadata(
    *,
    build: int,
    version: tuple[int, int, int] = (0, 1, 0),
    protocol: int = 7,
    database_schema: int = 14,
    revision: str | None = "a" * 40,
) -> ReleaseMetadata:
    return ReleaseMetadata(
        bundle_identifier="ai.ally.personal",
        ally_version=".".join(str(part) for part in version),
        short_version=version,
        build_version=build,
        bridge_protocol_version=protocol,
        database_schema_version=database_schema,
        source_revision=revision,
    )


def _executable(path: Path, label: str) -> Path:
    path.write_text(f"#!/bin/sh\necho {label}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _bundle(tmp_path: Path, name: str, *, build: int, revision: str | None) -> Path:
    app_binary = _executable(tmp_path / f"{name}-app", f"{name}-app")
    helper = _executable(tmp_path / f"{name}-helper", f"{name}-helper")
    output = tmp_path / f"{name}.app"
    command = [
        sys.executable,
        str(BUNDLE_SCRIPT),
        "assemble",
        "--app-executable",
        str(app_binary),
        "--helper",
        str(helper),
        "--output",
        str(output),
        "--build-version",
        str(build),
    ]
    if revision is not None:
        command.extend(["--source-revision", revision])
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output


def test_database_schema_release_constant_tracks_migration_tail() -> None:
    assert MIGRATIONS
    assert CURRENT_SCHEMA_VERSION == MIGRATIONS[-1].version


def test_forward_update_is_accepted_and_schema_bump_requires_backup() -> None:
    decision = compare_release_metadata(
        _metadata(build=7),
        _metadata(build=8, database_schema=15, revision="b" * 40),
        expected_bundle_identifier="ai.ally.personal",
    )

    assert decision.current_build_version == 7
    assert decision.candidate_build_version == 8
    assert decision.candidate_source_revision == "b" * 40
    assert decision.requires_pre_migration_backup is True


@pytest.mark.parametrize(
    ("current", "candidate", "message"),
    [
        (_metadata(build=7), _metadata(build=7), "same-build"),
        (_metadata(build=8), _metadata(build=7), "rollback"),
        (
            _metadata(build=7, version=(0, 2, 0)),
            _metadata(build=8, version=(0, 1, 9)),
            "semantic version",
        ),
        (
            _metadata(build=7, protocol=8),
            _metadata(build=8, protocol=7),
            "bridge protocol",
        ),
        (
            _metadata(build=7, database_schema=15),
            _metadata(build=8, database_schema=14),
            "database schema",
        ),
        (
            _metadata(build=7),
            _metadata(build=8, revision=None),
            "source revision",
        ),
    ],
)
def test_update_policy_rejects_non_forward_candidates(
    current: ReleaseMetadata,
    candidate: ReleaseMetadata,
    message: str,
) -> None:
    with pytest.raises(UpdateTrustError, match=message):
        compare_release_metadata(
            current,
            candidate,
            expected_bundle_identifier="ai.ally.personal",
        )


def test_codesign_identity_requires_exact_bundle_and_team() -> None:
    identity = parse_codesign_identity(
        "Executable=/Applications/Ally.app/Contents/MacOS/AllyDesktop\n"
        "CodeDirectory v=20500 size=999 flags=0x10000(runtime) hashes=1+0 location=embedded\n"
        "Identifier=ai.ally.personal\n"
        "TeamIdentifier=ABCDE12345\n"
        "Timestamp=Sep 25, 2026 at 01:00:00\n"
    )

    assert identity == ReleaseIdentity(
        bundle_identifier="ai.ally.personal",
        team_identifier="ABCDE12345",
        hardened_runtime=True,
        has_timestamp=True,
    )
    require_signing_identity(
        identity,
        expected_bundle_identifier="ai.ally.personal",
        expected_team_identifier="ABCDE12345",
    )

    with pytest.raises(UpdateTrustError, match="team"):
        require_signing_identity(
            identity,
            expected_bundle_identifier="ai.ally.personal",
            expected_team_identifier="ZZZZZ99999",
        )


def test_structural_compare_cli_is_path_free_and_forward_only(tmp_path: Path) -> None:
    current = _bundle(tmp_path, "Current", build=7, revision="a" * 40)
    candidate = _bundle(tmp_path, "Candidate", build=8, revision="b" * 40)

    accepted = subprocess.run(
        [
            sys.executable,
            str(UPDATE_SCRIPT),
            "compare",
            "--current",
            str(current),
            "--candidate",
            str(candidate),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(accepted.stdout)
    assert payload["status"] == "accepted"
    assert payload["current_build_version"] == 7
    assert payload["candidate_build_version"] == 8
    assert str(tmp_path) not in accepted.stdout

    rejected = subprocess.run(
        [
            sys.executable,
            str(UPDATE_SCRIPT),
            "compare",
            "--current",
            str(candidate),
            "--candidate",
            str(current),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "rollback" in rejected.stderr.lower()


def test_structural_compare_requires_release_grade_candidate_revision(
    tmp_path: Path,
) -> None:
    current = _bundle(tmp_path, "Current", build=7, revision="a" * 40)
    candidate = _bundle(tmp_path, "Candidate", build=8, revision=None)

    result = subprocess.run(
        [
            sys.executable,
            str(UPDATE_SCRIPT),
            "compare",
            "--current",
            str(current),
            "--candidate",
            str(candidate),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "source revision" in result.stderr.lower()


def test_codesign_identity_rejects_missing_runtime_or_timestamp() -> None:
    base = ReleaseIdentity(
        bundle_identifier="ai.ally.personal",
        team_identifier="ABCDE12345",
        hardened_runtime=False,
        has_timestamp=True,
    )
    with pytest.raises(UpdateTrustError, match="hardened runtime"):
        require_signing_identity(
            base,
            expected_bundle_identifier="ai.ally.personal",
            expected_team_identifier="ABCDE12345",
        )

    without_timestamp = ReleaseIdentity(
        bundle_identifier="ai.ally.personal",
        team_identifier="ABCDE12345",
        hardened_runtime=True,
        has_timestamp=False,
    )
    with pytest.raises(UpdateTrustError, match="timestamp"):
        require_signing_identity(
            without_timestamp,
            expected_bundle_identifier="ai.ally.personal",
            expected_team_identifier="ABCDE12345",
        )
