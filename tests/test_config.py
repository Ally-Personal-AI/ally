from pathlib import Path

from ally.config import default_paths


def test_default_paths_are_absolute_and_separate() -> None:
    paths = default_paths()

    assert isinstance(paths.config_dir, Path)
    assert isinstance(paths.data_dir, Path)
    assert paths.config_dir.is_absolute()
    assert paths.data_dir.is_absolute()
    assert paths.config_dir != paths.data_dir
