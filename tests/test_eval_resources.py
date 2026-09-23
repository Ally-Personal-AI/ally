"""Bundled evaluation defaults cannot be replaced by the working directory."""

import json
from pathlib import Path

import pytest

from ally.cli import main
from ally.evals.loader import load_eval_cases
from ally.evals.resources import EvaluationSuite, evaluation_case_file


@pytest.mark.parametrize(
    "suite, count",
    [
        ("core", 10),
        ("provider-smoke", 4),
        ("behavioral-qualification", 10),
    ],
)
def test_packaged_cases_ignore_working_directory(
    suite: EvaluationSuite,
    count: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shadow = tmp_path / "evals" / "cases" / f"{suite}.jsonl"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("This is not an evaluation suite.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with evaluation_case_file(suite) as path:
        assert len(load_eval_cases(path)) == count
        assert not path.is_relative_to(tmp_path)


def test_core_cli_defaults_and_explicit_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["eval", "run", "--json"]) == 0
    bundled = json.loads(capsys.readouterr().out)
    assert bundled["passed"] == bundled["total"] == 10

    # An explicit custom suite is honored, including its failure status.
    override = tmp_path / "custom.jsonl"
    override.write_text(json.dumps({
        "id": "synthetic-override",
        "category": "private_grounding_policy",
        "input": {
            "endpoint": "http://127.0.0.1:8080/v1",
            "allow_remote_private_context": False,
        },
        "expected": {"allowed": False},
    }) + "\n", encoding="utf-8")
    assert main(["eval", "run", str(override), "--json"]) == 1
    custom = json.loads(capsys.readouterr().out)
    assert custom["total"] == custom["failed"] == 1
    assert "synthetic-override" in json.dumps(custom)
