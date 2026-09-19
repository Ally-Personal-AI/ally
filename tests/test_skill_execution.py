import os
import sys
from pathlib import Path

import pytest

from ally.skills import (
    MAX_SKILL_INPUT_BYTES,
    InstalledSkillRuntime,
    LocalSkillManager,
    SkillExecutionError,
)
from ally.storage.sqlite import SQLiteDatabase, SQLiteSkillExecutionAuditStore


def write_executable_skill(
    root: Path,
    *,
    entrypoint: str = "skill_code:run",
    execution: bool = True,
    code: str,
) -> Path:
    root.mkdir(parents=True)
    lines = [
        'id = "sample.skill"',
        'name = "Sample Skill"',
        'version = "1.0.0"',
        'description = "Synthetic executable skill."',
        f'entrypoint = "{entrypoint}"',
    ]
    if execution:
        lines.append('execution = "python_subprocess_v1"')
    (root / "skill.toml").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    (root / "skill_code.py").write_text(code, encoding="utf-8")
    return root


def build_runtime(
    tmp_path: Path,
    source: Path,
    *,
    enable: bool = True,
) -> tuple[
    LocalSkillManager,
    SQLiteSkillExecutionAuditStore,
    InstalledSkillRuntime,
]:
    manager = LocalSkillManager(tmp_path / "installed")
    manager.install(source, available_tools=())
    if enable:
        manager.set_enabled("sample.skill", "1.0.0", enabled=True)
    audit = SQLiteSkillExecutionAuditStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    return manager, audit, InstalledSkillRuntime(manager, audit)


def test_enabled_skill_executes_in_child_without_parent_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="""
import os

def run(data):
    print("must not become protocol output")
    return {
        "echo": data["value"],
        "inherited_secret": os.environ.get("ALLY_TEST_SECRET"),
    }
""".strip()
        + "\n",
    )
    monkeypatch.setenv("ALLY_TEST_SECRET", "must-not-reach-child")
    _, audit, runtime = build_runtime(tmp_path, source)

    assert "skill_code" not in sys.modules
    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={"value": 42},
    )

    assert result.status == "succeeded"
    assert result.result == {
        "echo": 42,
        "inherited_secret": None,
    }
    assert result.error_class is None
    assert result.audit_id is not None
    assert "skill_code" not in sys.modules

    records = audit.list()
    assert len(records) == 1
    assert records[0].id == result.audit_id
    assert records[0].status == "succeeded"
    assert records[0].error_class is None


def test_disabled_skill_is_rejected_before_process_and_audit(
    tmp_path: Path,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="def run(data):\n    return data\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source, enable=False)

    with pytest.raises(SkillExecutionError, match="disabled"):
        runtime.execute(
            "sample.skill",
            "1.0.0",
            input_data={},
        )

    assert audit.list() == ()


def test_legacy_entrypoint_without_execution_opt_in_is_not_runnable(
    tmp_path: Path,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        execution=False,
        code="def run(data):\n    return data\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    with pytest.raises(SkillExecutionError, match="not executable"):
        runtime.execute(
            "sample.skill",
            "1.0.0",
            input_data={},
        )

    assert audit.list() == ()


def test_skill_exception_persists_only_error_class(tmp_path: Path) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="""
def run(data):
    raise RuntimeError("SECRET_EXCEPTION_MESSAGE")
""".strip()
        + "\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={},
    )

    assert result.status == "failed"
    assert result.result is None
    assert result.error_class == "RuntimeError"
    records = audit.list()
    assert len(records) == 1
    assert records[0].error_class == "RuntimeError"
    assert not hasattr(records[0], "stdout")
    assert not hasattr(records[0], "stderr")


def test_skill_timeout_is_bounded_and_audited(tmp_path: Path) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="""
import time

def run(data):
    time.sleep(10)
    return {}
""".strip()
        + "\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={},
        timeout_seconds=1,
    )

    assert result.status == "timed_out"
    assert result.error_class == "SkillExecutionTimeout"
    assert audit.list()[0].status == "timed_out"


def test_native_stdout_flood_is_killed_at_output_limit(tmp_path: Path) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="""
import os

def run(data):
    os.write(1, b"x" * 70000)
    return {}
""".strip()
        + "\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={},
    )

    assert result.status == "output_limit"
    assert result.error_class == "SkillOutputLimitExceeded"
    assert audit.list()[0].status == "output_limit"


def test_native_stderr_invalidates_protocol_without_persisting_content(
    tmp_path: Path,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="""
import os

def run(data):
    os.write(2, b"SECRET_STDERR")
    return {"ok": True}
""".strip()
        + "\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={},
    )

    assert result.status == "protocol_error"
    assert result.error_class == "SkillProtocolError"
    record = audit.list()[0]
    assert record.error_class == "SkillProtocolError"
    assert not hasattr(record, "stderr")


def test_entrypoint_module_must_resolve_inside_installed_package(
    tmp_path: Path,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        entrypoint="json:dumps",
        code="def run(data):\n    return data\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={},
    )

    assert result.status == "failed"
    assert result.error_class == "SkillEntrypointOutsidePackage"
    assert audit.list()[0].error_class == "SkillEntrypointOutsidePackage"


def test_post_install_symlink_mutation_is_rejected_before_execution(
    tmp_path: Path,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="def run(data):\n    return data\n",
    )
    manager, audit, runtime = build_runtime(tmp_path, source)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    installed_root = manager.root / "sample.skill" / "1.0.0"
    (installed_root / "late-link.txt").symlink_to(outside)

    with pytest.raises(SkillExecutionError, match="symlink"):
        runtime.execute(
            "sample.skill",
            "1.0.0",
            input_data={},
        )

    assert audit.list() == ()


def test_skill_input_size_and_timeout_configuration_are_bounded(
    tmp_path: Path,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="def run(data):\n    return data\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    with pytest.raises(SkillExecutionError, match="input exceeds"):
        runtime.execute(
            "sample.skill",
            "1.0.0",
            input_data={"value": "x" * MAX_SKILL_INPUT_BYTES},
        )

    with pytest.raises(SkillExecutionError, match="timeout_seconds"):
        runtime.execute(
            "sample.skill",
            "1.0.0",
            input_data={},
            timeout_seconds=0,
        )

    assert audit.list() == ()


def test_execution_result_is_json_only(tmp_path: Path) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="""
def run(data):
    return object()
""".strip()
        + "\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={},
    )

    assert result.status == "failed"
    assert result.error_class == "TypeError"
    assert audit.list()[0].error_class == "TypeError"


def test_isolated_skill_cannot_import_parent_ally_package(
    tmp_path: Path,
) -> None:
    source = write_executable_skill(
        tmp_path / "source",
        code="""
def run(data):
    try:
        import ally
    except ModuleNotFoundError:
        return {"ally_importable": False}
    return {"ally_importable": True}
""".strip()
        + "\n",
    )
    _, audit, runtime = build_runtime(tmp_path, source)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={},
    )

    assert result.status == "succeeded"
    assert result.result == {"ally_importable": False}
    assert audit.list()[0].status == "succeeded"


def test_nested_skill_module_entrypoint_executes_from_package(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir(parents=True)
    (root / "skill.toml").write_text(
        "\n".join(
            [
                'id = "sample.skill"',
                'name = "Sample Skill"',
                'version = "1.0.0"',
                'description = "Nested synthetic executable skill."',
                'entrypoint = "nested.worker:run"',
                'execution = "python_subprocess_v1"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    nested = root / "nested"
    nested.mkdir()
    (nested / "__init__.py").write_text("", encoding="utf-8")
    (nested / "worker.py").write_text(
        "def run(data):\n    return {'nested': data['value']}\n",
        encoding="utf-8",
    )
    _, audit, runtime = build_runtime(tmp_path, root)

    result = runtime.execute(
        "sample.skill",
        "1.0.0",
        input_data={"value": 7},
    )

    assert result.status == "succeeded"
    assert result.result == {"nested": 7}
    assert audit.list()[0].status == "succeeded"
