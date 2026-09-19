"""Regression tests for the least-privilege security workflow."""

from pathlib import Path


def test_security_workflow_is_active_and_least_privilege() -> None:
    workflow = Path(".github/workflows/security.yml").read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "uv sync --locked --extra security" in workflow
    assert "pip-audit --strict --require-hashes --disable-pip" in workflow
    assert "zizmor --offline --strict-collection" in workflow


def test_all_third_party_actions_are_pinned_to_commit_shas() -> None:
    workflow_root = Path(".github/workflows")

    for workflow_path in workflow_root.glob("*.yml"):
        for line in workflow_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            reference = stripped.split("@", maxsplit=1)[1].split(maxsplit=1)[0]
            assert len(reference) == 40, f"unpinned action in {workflow_path}: {line}"
            assert all(character in "0123456789abcdef" for character in reference), (
                f"non-SHA action reference in {workflow_path}: {line}"
            )
