"""Human-facing non-secret configuration commands."""

from __future__ import annotations

import json

from ally.configuration import (
    ConfigFileError,
    FileConfigStore,
    default_config_path,
)


def run_config_path() -> int:
    print(default_config_path())
    return 0


def run_config_init() -> int:
    path = default_config_path()
    store = FileConfigStore(path)
    try:
        store.initialize()
    except FileExistsError as exc:
        print(f"Config error: {exc}")
        return 2

    print(path)
    return 0


def run_config_show() -> int:
    store = FileConfigStore(default_config_path())
    try:
        config = store.load_or_default()
    except ConfigFileError as exc:
        print(f"Config error: {exc}")
        return 2

    print(
        json.dumps(
            config.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def run_config_validate() -> int:
    path = default_config_path()
    store = FileConfigStore(path)
    if not path.exists():
        print(f"Config error: config does not exist: {path}")
        return 2

    try:
        store.load()
    except ConfigFileError as exc:
        print(f"Config error: {exc}")
        return 2

    print("Configuration validation: ok")
    return 0
