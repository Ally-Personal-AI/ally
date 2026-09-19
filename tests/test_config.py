from pathlib import Path

import pytest

from ally.config import default_paths


def test_default_paths_are_absolute_and_separate() -> None:
    paths = default_paths()

    assert isinstance(paths.config_dir, Path)
    assert isinstance(paths.data_dir, Path)
    assert paths.config_dir.is_absolute()
    assert paths.data_dir.is_absolute()
    assert paths.config_dir != paths.data_dir


def test_colliding_platform_paths_are_namespaced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    shared = tmp_path / "Application Support" / "Ally"
    monkeypatch.setattr(
        "ally.config.user_config_dir",
        lambda *_args: str(shared),
    )
    monkeypatch.setattr(
        "ally.config.user_data_dir",
        lambda *_args: str(shared),
    )

    paths = default_paths()

    assert paths.config_dir == shared / "config"
    assert paths.data_dir == shared / "data"
