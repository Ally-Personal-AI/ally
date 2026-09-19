"""Human and machine-readable evaluation reporting."""

from __future__ import annotations

import json

from ally.evals.models import EvalSummary


def render_text_summary(summary: EvalSummary) -> str:
    lines = [
        (
            f"Evaluations: {summary.total} total, {summary.passed} passed, "
            f"{summary.failed} failed, {summary.errors} errors"
        )
    ]
    for result in summary.results:
        marker = {
            "passed": "PASS",
            "failed": "FAIL",
            "error": "ERROR",
        }[result.status]
        detail = f" — {result.message}" if result.message else ""
        lines.append(f"[{marker}] {result.case_id} ({result.category}){detail}")
    return "\n".join(lines)


def render_json_summary(summary: EvalSummary) -> str:
    return json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True)
