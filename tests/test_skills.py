from pathlib import Path

import pytest

from ally.skills import SkillCatalog, load_skill_package
from ally.skills.loader import SkillManifestError
from ally.skills.models import SkillConfigField, SkillManifest


def write_skill(root: Path, manifest: str) -> Path:
    root.mkdir()
    (root / "skill.toml").write_text(manifest, encoding="utf-8")
    return root


def test_load_skill_package_is_data_only_and_validated(tmp_path: Path) -> None:
    root = write_skill(
        tmp_path / "sample",
        """
schema_version = 1
id = "sample.skill"
name = "Sample Skill"
version = "0.1.0"
description = "Synthetic skill for tests."
entrypoint = "sample_skill:run"
required_tools = ["system.info"]
optional_tools = ["calendar.read"]

[config.mode]
type = "string"
description = "Synthetic operating mode."
required = true
""".strip(),
    )

    package = load_skill_package(root)

    assert package.manifest.id == "sample.skill"
    assert package.manifest.entrypoint == "sample_skill:run"
    assert package.manifest.required_tools == ("system.info",)
    assert package.manifest.config["mode"].required is True


def test_skill_manifest_rejects_overlapping_tool_declarations() -> None:
    with pytest.raises(ValueError, match="both required and optional"):
        SkillManifest(
            id="sample.skill",
            name="Sample",
            version="1.0.0",
            description="Synthetic.",
            required_tools=("same.tool",),
            optional_tools=("same.tool",),
        )


def test_loader_rejects_missing_manifest(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    root.mkdir()

    with pytest.raises(SkillManifestError, match="Missing skill manifest"):
        load_skill_package(root)


def test_loader_rejects_invalid_toml(tmp_path: Path) -> None:
    root = write_skill(tmp_path / "bad", "this = [")

    with pytest.raises(SkillManifestError, match="Invalid TOML"):
        load_skill_package(root)


def test_catalog_reports_missing_required_tools(tmp_path: Path) -> None:
    root = write_skill(
        tmp_path / "sample",
        """
id = "sample.skill"
name = "Sample"
version = "1.0.0"
description = "Synthetic."
required_tools = ["system.info", "files.read"]
""".strip(),
    )
    package = load_skill_package(root)

    missing = SkillCatalog.missing_required_tools(
        package,
        available_tools=("system.info",),
    )

    assert missing == ("files.read",)


def test_catalog_rejects_duplicate_skill_ids(tmp_path: Path) -> None:
    root = write_skill(
        tmp_path / "sample",
        """
id = "sample.skill"
name = "Sample"
version = "1.0.0"
description = "Synthetic."
""".strip(),
    )
    package = load_skill_package(root)
    catalog = SkillCatalog()
    catalog.register(package)

    with pytest.raises(ValueError, match="already registered"):
        catalog.register(package)


def test_loader_rejects_unknown_manifest_fields(tmp_path: Path) -> None:
    root = write_skill(
        tmp_path / "unknown",
        """
id = "sample.skill"
name = "Sample"
version = "1.0.0"
description = "Synthetic."
unexpected_permission = "all"
""".strip(),
    )

    with pytest.raises(SkillManifestError, match="Invalid skill manifest"):
        load_skill_package(root)


def test_subprocess_execution_requires_explicit_entrypoint() -> None:
    with pytest.raises(ValueError, match="requires an entrypoint"):
        SkillManifest(
            id="sample.skill",
            name="Sample",
            version="1.0.0",
            description="Synthetic.",
            execution="python_subprocess_v1",
        )


def test_subprocess_execution_v1_exposes_no_tools_or_config() -> None:
    with pytest.raises(ValueError, match="does not expose Ally tools"):
        SkillManifest(
            id="sample.skill",
            name="Sample",
            version="1.0.0",
            description="Synthetic.",
            entrypoint="sample:run",
            execution="python_subprocess_v1",
            required_tools=("system.info",),
        )

    with pytest.raises(ValueError, match="does not expose skill config"):
        SkillManifest(
            id="sample.skill",
            name="Sample",
            version="1.0.0",
            description="Synthetic.",
            entrypoint="sample:run",
            execution="python_subprocess_v1",
            config={
                "mode": SkillConfigField(
                    type="string",
                    description="Synthetic mode.",
                )
            },
        )


def test_entrypoint_alone_does_not_grant_execution() -> None:
    manifest = SkillManifest(
        id="sample.skill",
        name="Sample",
        version="1.0.0",
        description="Synthetic.",
        entrypoint="sample:run",
    )

    assert manifest.entrypoint == "sample:run"
    assert manifest.execution is None


def test_manifest_rejects_malformed_dotted_entrypoint() -> None:
    with pytest.raises(ValueError, match="entrypoint"):
        SkillManifest(
            id="sample.skill",
            name="Sample",
            version="1.0.0",
            description="Synthetic.",
            entrypoint="package..module:run",
            execution="python_subprocess_v1",
        )
