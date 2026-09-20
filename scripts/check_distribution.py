"""Build and exercise the wheel from an sdist in a fresh runtime environment.

Run with: uv run --locked --group build python scripts/check_distribution.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile


def run(arguments: list[str], *, cwd: Path) -> None:
    subprocess.run(arguments, cwd=cwd, check=True, timeout=300)


def check_wheel(wheel: Path, repository: Path) -> None:
    """Require every source module and frozen fixture in the built wheel."""

    source = repository / "src"
    expected = {
        path.relative_to(source).as_posix()
        for path in (source / "ally").rglob("*")
        if path.is_file() and path.suffix in (".py", ".jsonl")
    }
    with ZipFile(wheel) as archive:
        members = set(archive.namelist())
        missing = expected - members
        if missing:
            raise RuntimeError(f"Wheel is missing package files: {sorted(missing)}")
        unexpected = {
            name for name in members
            if name.startswith("ally/") and name not in expected
        }
        if unexpected:
            raise RuntimeError(f"Wheel includes unexpected package files: {sorted(unexpected)}")


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv must be on PATH")
    with TemporaryDirectory(prefix="ally-distribution-") as temporary:
        root = Path(temporary).resolve()
        artifacts = root / "dist"
        # Default uv build builds an sdist, then builds its wheel from that sdist.
        # The build group supplies the backend from uv.lock, including transitives.
        run(
            [
                uv, "build", "--no-sources", "--no-build-isolation",
                "--python", sys.executable, "--out-dir", str(artifacts),
            ],
            cwd=repository,
        )
        wheels = tuple(artifacts.glob("*.whl"))
        if len(wheels) != 1 or len(tuple(artifacts.glob("*.tar.gz"))) != 1:
            raise RuntimeError("Expected exactly one fresh sdist and one wheel")
        wheel = wheels[0]
        check_wheel(wheel, repository)
        requirements = root / "runtime-requirements.txt"
        run(
            [
                uv, "export", "--locked", "--no-dev", "--no-default-groups",
                "--no-emit-project", "--quiet", "--output-file", str(requirements),
            ],
            cwd=repository,
        )
        environment = root / "venv"
        run([uv, "venv", "--python", sys.executable, str(environment)], cwd=root)
        python = environment / "bin" / "python"
        run(
            [
                uv, "pip", "sync", "--python", str(python), "--require-hashes",
                str(requirements),
            ],
            cwd=root,
        )
        run(
            [
                uv, "pip", "install", "--python", str(python),
                "--no-deps", "--no-index", str(wheel),
            ],
            cwd=root,
        )
        run([uv, "pip", "check", "--python", str(python)], cwd=root)
        work = root / "work"
        work.mkdir()
        smoke = work / "installed_smoke.py"
        shutil.copy2(repository / "scripts" / "installed_smoke.py", smoke)
        run([str(python), "-I", str(smoke)], cwd=work)
    print("Distribution check passed: sdist, wheel, clean install, synthetic workflows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
