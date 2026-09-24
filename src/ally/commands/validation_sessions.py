"""Commands for resumable validation sessions."""

from __future__ import annotations

import json
from pathlib import Path

from ally.validation_sessions import (
    ValidationSessionError,
    ValidationSessionManifest,
    ValidationSessionStatus,
    initialize_validation_session,
    inspect_validation_session,
    load_validation_session,
)


def _render_status(status: ValidationSessionStatus) -> None:
    print(f"Candidate: {status.candidate_label}")
    print(f"Session ID: {status.session_id}")
    for stage in (
        status.readiness,
        status.capability,
        status.workflows,
        status.privacy,
        status.profile,
    ):
        suffix = (
            ""
            if stage.artifact_sha256 is None
            else f" sha256={stage.artifact_sha256}"
        )
        print(
            f"[{stage.state.upper()}] {stage.id}: {stage.detail}{suffix}"
        )
    print(f"Next step: {status.next_step}")
    print(f"Complete: {'yes' if status.complete else 'no'}")


def run_init_validation_session(
    *,
    candidate_label: str,
    directory: str,
    json_output: bool,
) -> int:
    """Create one immutable session plan in an isolated directory."""

    try:
        manifest, path = initialize_validation_session(
            directory=Path(directory),
            candidate_label=candidate_label,
        )
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Validation session error: {exc}")
        return 2

    if json_output:
        rendered = manifest.model_dump(mode="json")
        rendered["session_path"] = str(path)
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        root = path.parent
        print(f"Validation session: {path}")
        print(f"Session ID: {manifest.session_id}")
        print(f"Candidate: {manifest.candidate_label}")
        print(f"Capability target: {root / manifest.artifacts.capability}")
        print(f"Workflow target: {root / manifest.artifacts.workflows}")
        print(f"Privacy target: {root / manifest.artifacts.privacy}")
        print(f"Profile target: {root / manifest.artifacts.profile}")
    return 0


def run_show_validation_session(
    *,
    session_path: str,
    json_output: bool,
) -> int:
    """Inspect the immutable session plan without evaluating evidence."""

    try:
        manifest: ValidationSessionManifest = load_validation_session(
            Path(session_path)
        )
    except ValidationSessionError as exc:
        print(f"Validation session error: {exc}")
        return 2

    if json_output:
        print(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(f"Session ID: {manifest.session_id}")
        print(f"Candidate: {manifest.candidate_label}")
        print(f"Ally version: {manifest.ally_version}")
        print(f"Capability artifact: {manifest.artifacts.capability}")
        print(f"Workflow artifact: {manifest.artifacts.workflows}")
        print(f"Privacy artifact: {manifest.artifacts.privacy}")
        print(f"Profile artifact: {manifest.artifacts.profile}")
    return 0


def run_refresh_validation_session(
    *,
    session_path: str,
    json_output: bool,
) -> int:
    """Recompute session state from live readiness and immutable evidence."""

    try:
        status = inspect_validation_session(Path(session_path))
    except ValidationSessionError as exc:
        print(f"Validation session error: {exc}")
        return 2

    if json_output:
        print(json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        _render_status(status)
    return 0


def run_verify_validation_session(
    *,
    session_path: str,
    json_output: bool,
) -> int:
    """Require the session to be fully and currently qualified."""

    try:
        status = inspect_validation_session(Path(session_path))
    except ValidationSessionError as exc:
        print(f"Validation session error: {exc}")
        return 2

    if json_output:
        print(json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        _render_status(status)
    return 0 if status.complete else 1
