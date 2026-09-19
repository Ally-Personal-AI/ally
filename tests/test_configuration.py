from pathlib import Path

import pytest
from pydantic import ValidationError

from ally.configuration import AllyConfig, ConfigFileError, FileConfigStore


def test_config_defaults_are_local_and_non_secret() -> None:
    config = AllyConfig()

    assert config.schema_version == 1
    assert config.inference.endpoint == "http://127.0.0.1:8080/v1"
    assert config.inference.model is None
    assert config.privacy.allow_remote_inference is False
    assert config.privacy.allow_private_context_remote is False
    assert "secret" not in config.model_dump_json().casefold()
    assert "token" not in config.model_dump_json().casefold()
    assert "api_key" not in config.model_dump_json().casefold()


def test_file_config_store_round_trips_atomically(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = FileConfigStore(path)

    initialized = store.initialize()

    assert path.is_file()
    assert store.load() == initialized
    assert store.load_or_default() == initialized


def test_file_config_store_returns_defaults_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = FileConfigStore(path)

    config = store.load_or_default()

    assert config == AllyConfig()
    assert not path.exists()


def test_file_config_store_refuses_to_overwrite_on_initialize(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    store = FileConfigStore(path)
    store.initialize()

    with pytest.raises(FileExistsError, match="already exists"):
        store.initialize()


def test_config_rejects_unknown_secret_like_fields() -> None:
    with pytest.raises(ValidationError, match="api_key"):
        AllyConfig.model_validate(
            {
                "schema_version": 1,
                "inference": {
                    "endpoint": "http://127.0.0.1:8080/v1",
                    "api_key": "must-not-be-config",
                },
            }
        )


def test_config_store_rejects_invalid_document(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version": 1, "password": "nope"}', encoding="utf-8")

    with pytest.raises(ConfigFileError, match="invalid Ally config"):
        FileConfigStore(path).load()
