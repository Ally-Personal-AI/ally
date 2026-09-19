import json
from pathlib import Path

import pytest
from pydantic import JsonValue

from ally.evals import EvalCase, EvaluationOutcome, EvaluationRunner, EvaluatorRegistry
from ally.evals.loader import load_eval_cases


class PassEvaluator:
    @property
    def name(self) -> str:
        return "pass"

    @property
    def category(self) -> str:
        return "synthetic"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        return EvaluationOutcome(passed=True, message=case.id)


class ErrorEvaluator:
    @property
    def name(self) -> str:
        return "error"

    @property
    def category(self) -> str:
        return "error"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        raise RuntimeError(f"synthetic error for {case.id}")


def test_loader_reads_jsonl_and_rejects_duplicate_ids(tmp_path: Path) -> None:
    case1: dict[str, JsonValue] = {
        "id": "case-1",
        "category": "synthetic",
        "input": {},
        "expected": {},
    }
    case2: dict[str, JsonValue] = {
        "id": "case-2",
        "category": "synthetic",
        "input": {},
        "expected": {},
    }
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(case1) + "\n" + json.dumps(case2) + "\n",
        encoding="utf-8",
    )

    loaded = load_eval_cases(path)

    assert [item.id for item in loaded] == ["case-1", "case-2"]

    path.write_text(
        json.dumps(case1) + "\n" + json.dumps(case1) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate"):
        load_eval_cases(path)


def test_runner_reports_passes_and_isolates_errors() -> None:
    registry = EvaluatorRegistry()
    registry.register(PassEvaluator())
    registry.register(ErrorEvaluator())
    runner = EvaluationRunner(registry)

    summary = runner.run(
        (
            EvalCase(id="pass-1", category="synthetic", input={}, expected={}),
            EvalCase(id="error-1", category="error", input={}, expected={}),
        )
    )

    assert summary.total == 2
    assert summary.passed == 1
    assert summary.errors == 1
    assert not summary.successful
