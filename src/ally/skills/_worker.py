"""Stdlib-only child process for python_subprocess_v1 skills.

This module is executed as a script by the parent process. It deliberately does
not import Ally so the skill is never loaded into the Ally Core interpreter.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

_ERROR_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")


class SkillWorkerProtocolError(RuntimeError):
    pass


class SkillEntrypointOutsidePackage(RuntimeError):
    pass


class SkillEntrypointNotCallable(RuntimeError):
    pass


def _safe_error_class(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if _ERROR_CLASS.fullmatch(name) is not None else "SkillError"


def _emit(payload: dict[str, Any]) -> None:
    rendered = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    sys.stdout.write(rendered)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _load_request() -> dict[str, Any]:
    raw = json.load(sys.stdin)
    if not isinstance(raw, dict):
        raise SkillWorkerProtocolError("request must be an object")
    if raw.get("protocol_version") != 1:
        raise SkillWorkerProtocolError("unsupported protocol version")
    input_value = raw.get("input")
    if not isinstance(input_value, dict):
        raise SkillWorkerProtocolError("input must be an object")
    return input_value


def _run(root: Path, entrypoint: str, input_value: dict[str, Any]) -> Any:
    module_name, function_name = entrypoint.split(":", maxsplit=1)
    sys.path.insert(0, str(root))

    with open(os.devnull, "w", encoding="utf-8") as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            module = importlib.import_module(module_name)
            module_file = getattr(module, "__file__", None)
            if module_file is None:
                raise SkillEntrypointOutsidePackage(
                    "entrypoint module has no package file"
                )
            resolved_module = Path(module_file).resolve()
            if not resolved_module.is_relative_to(root):
                raise SkillEntrypointOutsidePackage(
                    "entrypoint module is outside skill package"
                )

            function = getattr(module, function_name, None)
            if not callable(function):
                raise SkillEntrypointNotCallable(
                    "entrypoint attribute is not callable"
                )
            return function(input_value)


def main() -> int:
    if len(sys.argv) != 3:
        _emit(
            {
                "protocol_version": 1,
                "ok": False,
                "error_class": "SkillWorkerProtocolError",
            }
        )
        return 2

    root = Path(sys.argv[1]).resolve()
    entrypoint = sys.argv[2]

    try:
        input_value = _load_request()
        result = _run(root, entrypoint, input_value)
        _emit(
            {
                "protocol_version": 1,
                "ok": True,
                "result": result,
            }
        )
        return 0
    except BaseException as exc:
        _emit(
            {
                "protocol_version": 1,
                "ok": False,
                "error_class": _safe_error_class(exc),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
