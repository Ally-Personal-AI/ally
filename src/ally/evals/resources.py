"""Location-independent access to the frozen, packaged evaluation suites."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

EvaluationSuite = Literal["core", "provider-smoke"]


@contextmanager
def evaluation_case_file(
    suite: EvaluationSuite,
    override: str | None = None,
) -> Generator[Path]:
    """Use an explicit file, or materialize the package's frozen suite.

    Never search the current working directory for an implicit default.
    Keep the context open while reading or fingerprinting a packaged resource.
    """

    if override is not None:
        yield Path(override).expanduser()
        return
    if suite not in ("core", "provider-smoke"):
        raise ValueError("unknown bundled evaluation suite")
    resource = files("ally.evals").joinpath("cases", f"{suite}.jsonl")
    with as_file(resource) as path:
        yield path
