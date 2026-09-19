from pathlib import Path

import pytest

from ally.skills import LocalSkillManager, SkillInstallationError


def write_skill(
    root: Path,
    *,
    skill_id: str = "sample.skill",
    version: str = "1.0.0",
    required_tools: tuple[str, ...] = (),
    entrypoint: str | None = None,
) -> Path:
    root.mkdir(parents=True)
    lines = [
        f'id = "{skill_id}"',
        'name = "Sample Skill"',
        f'version = "{version}"',
        'description = "Synthetic skill package."',
    ]
    if entrypoint is not None:
        lines.append(f'entrypoint = "{entrypoint}"')
    if required_tools:
        rendered = ", ".join(f'"{tool}"' for tool in required_tools)
        lines.append(f"required_tools = [{rendered}]")

    (root / "skill.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_install_copies_package_disabled_without_importing_entrypoint(
    tmp_path: Path,
) -> None:
    source = write_skill(
        tmp_path / "source",
        entrypoint="boom:run",
    )
    (source / "boom.py").write_text(
        'raise RuntimeError("must never import during install")\n',
        encoding="utf-8",
    )
    manager = LocalSkillManager(tmp_path / "installed")

    installation = manager.install(source, available_tools=())

    assert installation.enabled is False
    assert installation.skill_id == "sample.skill"
    installed_root = tmp_path / "installed" / "sample.skill" / "1.0.0"
    assert (installed_root / "skill.toml").is_file()
    assert (installed_root / "boom.py").is_file()
    assert source.is_dir()
    installed = manager.load_package("sample.skill", "1.0.0")
    assert installed.manifest.entrypoint == "boom:run"


def test_install_rejects_missing_required_tools(tmp_path: Path) -> None:
    source = write_skill(
        tmp_path / "source",
        required_tools=("files.read",),
    )
    manager = LocalSkillManager(tmp_path / "installed")

    with pytest.raises(SkillInstallationError, match=r"missing required tools: files\.read"):
        manager.install(source, available_tools=("system.info",))

    assert manager.list() == ()


def test_install_rejects_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    source = write_skill(tmp_path / "source")
    (source / "linked.txt").symlink_to(outside)
    manager = LocalSkillManager(tmp_path / "installed")

    with pytest.raises(SkillInstallationError, match="symlinks"):
        manager.install(source, available_tools=())


def test_install_rejects_reserved_metadata_file(tmp_path: Path) -> None:
    source = write_skill(tmp_path / "source")
    (source / ".ally-installation.json").write_text("{}", encoding="utf-8")
    manager = LocalSkillManager(tmp_path / "installed")

    with pytest.raises(SkillInstallationError, match="reserved metadata"):
        manager.install(source, available_tools=())


def test_enable_one_version_disables_other_version(tmp_path: Path) -> None:
    root = tmp_path / "installed"
    manager = LocalSkillManager(root)
    manager.install(
        write_skill(tmp_path / "v1", version="1.0.0"),
        available_tools=(),
    )
    manager.install(
        write_skill(tmp_path / "v2", version="2.0.0"),
        available_tools=(),
    )

    first = manager.set_enabled("sample.skill", "1.0.0", enabled=True)
    second = manager.set_enabled("sample.skill", "2.0.0", enabled=True)

    assert first.enabled is True
    assert second.enabled is True
    loaded_first = manager.get("sample.skill", "1.0.0")
    loaded_second = manager.get("sample.skill", "2.0.0")
    assert loaded_first is not None
    assert loaded_second is not None
    assert loaded_first.enabled is False
    assert loaded_second.enabled is True


def test_uninstall_removes_copy_but_preserves_source(tmp_path: Path) -> None:
    source = write_skill(tmp_path / "source")
    manager = LocalSkillManager(tmp_path / "installed")
    manager.install(source, available_tools=())

    removed = manager.uninstall("sample.skill", "1.0.0")

    assert removed.skill_id == "sample.skill"
    assert manager.get("sample.skill", "1.0.0") is None
    assert source.is_dir()
    assert (source / "skill.toml").is_file()


def test_management_rejects_path_traversal_selectors(tmp_path: Path) -> None:
    manager = LocalSkillManager(tmp_path / "installed")

    with pytest.raises(SkillInstallationError, match="invalid skill ID"):
        manager.get("../escape", "1.0.0")

    with pytest.raises(SkillInstallationError, match="invalid skill version"):
        manager.get("sample.skill", "../1.0.0")
