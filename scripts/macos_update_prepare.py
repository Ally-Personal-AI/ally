"""Verify and prepare a macOS Ally update without replacing the application."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import macos_update_trust
from ally.release.update_preparation import (
    UpdatePreparationError,
    prepare_update,
)
from ally.storage import default_database_path
from ally.storage.sqlite import SQLiteDatabase


def _render(record: object) -> str:
    payload: dict[str, Any] = asdict(record)  # type: ignore[arg-type]
    payload["status"] = "prepared"
    return json.dumps(payload, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a signed/notarized forward Ally.app candidate and satisfy "
            "pre-install backup requirements without replacing application code."
        )
    )
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument(
        "--backup-output",
        type=Path,
        help=(
            "Fresh Ally backup path. Required when the candidate raises the "
            "database schema; optional otherwise."
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        help=(
            "Database to back up; defaults to Ally's normal local database. "
            "Ignored unless --backup-output is supplied."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        decision = macos_update_trust.verify_update(
            args.current,
            args.candidate,
            expected_team_identifier=args.team_id,
        )
        database = None
        if args.backup_output is not None:
            database = SQLiteDatabase(
                default_database_path() if args.database is None else args.database
            )
        record = prepare_update(
            decision,
            database=database,
            backup_destination=args.backup_output,
        )
        print(_render(record))
        return 0
    except (
        macos_update_trust.UpdateTrustError,
        UpdatePreparationError,
    ) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
