"""Static architecture checks for Ally's package dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parents[1] / "src" / "ally"

# These packages are allowed to know about concrete SQLite because they are
# composition/infrastructure edges rather than reusable domain/runtime code.
SQLITE_IMPLEMENTATION_ALLOWED = {
    "commands",
    "diagnostics",
    "portability",
    "storage",
}


def _imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            continue

        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )

    return tuple(sorted(imported))


def _python_modules() -> tuple[Path, ...]:
    return tuple(sorted(SRC_ROOT.rglob("*.py")))


def _relative(path: Path) -> Path:
    return path.relative_to(SRC_ROOT)


def _imports_prefix(imported: tuple[str, ...], prefix: str) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported
    )


def test_command_layer_does_not_leak_into_core_packages() -> None:
    """Only the CLI/composition layer may import ally.commands."""

    violations: list[str] = []
    for path in _python_modules():
        relative = _relative(path)
        if relative == Path("cli.py") or relative.parts[0] == "commands":
            continue

        imported = _imported_modules(path)
        if _imports_prefix(imported, "ally.commands"):
            violations.append(str(relative))

    assert violations == [], (
        "Core packages must not import ally.commands; move composition into "
        f"the command/interface layer. Violations: {violations}"
    )


def test_cli_module_does_not_leak_into_packages() -> None:
    """No reusable package may depend on the executable CLI module."""

    violations: list[str] = []
    for path in _python_modules():
        relative = _relative(path)
        if relative == Path("cli.py"):
            continue

        imported = _imported_modules(path)
        if _imports_prefix(imported, "ally.cli"):
            violations.append(str(relative))

    assert violations == [], (
        "Reusable Ally packages must not import ally.cli. "
        f"Violations: {violations}"
    )


def test_core_packages_do_not_import_sqlite_implementation() -> None:
    """Domain/runtime code depends on storage contracts, not SQLite adapters."""

    violations: list[str] = []
    for path in _python_modules():
        relative = _relative(path)
        top_level = relative.parts[0]
        if top_level in SQLITE_IMPLEMENTATION_ALLOWED:
            continue

        imported = _imported_modules(path)
        if _imports_prefix(imported, "ally.storage.sqlite"):
            violations.append(str(relative))

    assert violations == [], (
        "Core/domain packages must not import ally.storage.sqlite; depend on "
        "Ally-owned protocols and compose concrete storage at the edge. "
        f"Violations: {violations}"
    )


NETWORK_TRANSPORT_PREFIXES = (
    "aiohttp",
    "http.client",
    "httpx",
    "requests",
    "socket",
    "urllib.request",
    "websockets",
)
NETWORK_TRANSPORT_ALLOWED_PREFIXES = (
    Path("egress"),
    Path("models/providers"),
)


def test_network_transport_is_confined_to_reviewed_boundaries() -> None:
    """Network-capable imports stay inside model-provider or egress adapters."""

    violations: list[str] = []
    for path in _python_modules():
        relative = _relative(path)
        if any(
            relative == prefix or relative.is_relative_to(prefix)
            for prefix in NETWORK_TRANSPORT_ALLOWED_PREFIXES
        ):
            continue

        imported = _imported_modules(path)
        if any(
            _imports_prefix(imported, prefix)
            for prefix in NETWORK_TRANSPORT_PREFIXES
        ):
            violations.append(str(relative))

    assert violations == [], (
        "Network transports must stay inside ally.models.providers or ally.egress; "
        f"route new external integrations through the controlled boundary. "
        f"Violations: {violations}"
    )
