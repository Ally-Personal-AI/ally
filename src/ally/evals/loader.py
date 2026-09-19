"""Frozen JSONL evaluation case loading."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ally.evals.models import EvalCase


def load_eval_cases(path: Path) -> tuple[EvalCase, ...]:
    """Load and validate newline-delimited JSON evaluation cases."""

    if not path.is_file():
        raise ValueError(f"Evaluation case file does not exist: {path}")

    cases: list[EvalCase] = []
    seen: set[str] = set()

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            payload = json.loads(line)
            case = EvalCase.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(
                f"Invalid evaluation case at {path}:{line_number}: {exc}"
            ) from exc

        if case.id in seen:
            raise ValueError(f"Duplicate evaluation case ID: {case.id}")
        seen.add(case.id)
        cases.append(case)

    if not cases:
        raise ValueError(f"Evaluation case file contains no cases: {path}")

    return tuple(cases)
