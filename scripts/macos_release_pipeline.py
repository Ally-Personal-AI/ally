"""Build a verified local macOS Ally release artifact in the required order."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal

import macos_app_bundle
import macos_release_signing
from ally.commands.release_readiness import run_verify_release_readiness
from ally.diagnostics.release_readiness import load_release_readiness_report

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_DESKTOP_PACKAGE = _REPOSITORY_ROOT / "desktop/macos"
_HELPER_BUILD_SCRIPT = _REPOSITORY_ROOT / "scripts/build_macos_desktop_helper.py"
_PYINSTALLER_VERSION = "6.22.3"
_PYINSTALLER_HOOKS_VERSION = "2026.7"

ReleaseBuildMode = Literal["adhoc", "production"]


class ReleaseBuildError(RuntimeError):
    """Raised when a release artifact cannot be built safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _capture(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if not value:
        raise ReleaseBuildError("release build command returned no output")
    return value


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ReleaseBuildError(f"required release tool is unavailable: {name}")
    return path


def _require_source_revision(source_revision: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise ReleaseBuildError(
            "source revision must be a full lowercase 40-character Git commit SHA"
        )


def _require_build_version(build_version: str) -> None:
    if re.fullmatch(r"[1-9]\d*", build_version) is None:
        raise ReleaseBuildError("build version must be a positive integer")


def _require_output_outside_repository(output_dir: Path) -> Path:
    destination = output_dir.expanduser().absolute()
    repository = _REPOSITORY_ROOT.resolve()
    try:
        resolved_parent = destination.parent.resolve()
    except OSError as exc:
        raise ReleaseBuildError("release output parent cannot be resolved") from exc
    resolved = resolved_parent / destination.name
    if resolved == repository or resolved.is_relative_to(repository):
        raise ReleaseBuildError("release output must be outside the repository")
    return resolved


def _require_checkout(source_revision: str) -> None:
    git = _require_tool("git")
    current = _capture([git, "rev-parse", "HEAD"], cwd=_REPOSITORY_ROOT)
    if current != source_revision:
        raise ReleaseBuildError(
            "source revision does not match the checked-out Git commit"
        )
    status = _capture_allow_empty(
        [git, "status", "--porcelain", "--untracked-files=normal"],
        cwd=_REPOSITORY_ROOT,
    )
    if status:
        raise ReleaseBuildError(
            "release builds require a clean Git working tree"
        )


def _capture_allow_empty(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _require_request(
    *,
    mode: ReleaseBuildMode,
    identity: str | None,
    notary_profile: str | None,
    release_readiness: Path | None,
    validation_session: Path | None,
    machine_acceptance: Path | None,
    clean: bool,
) -> None:
    production_values = (
        identity,
        notary_profile,
        release_readiness,
        validation_session,
        machine_acceptance,
    )
    if mode == "adhoc":
        if any(value is not None for value in production_values):
            raise ReleaseBuildError(
                "ad-hoc builds must not accept production signing/readiness options"
            )
        return

    if clean:
        raise ReleaseBuildError(
            "production builds never replace an existing release output"
        )
    if (
        identity is None
        or not identity.strip()
        or identity.strip() == "-"
        or notary_profile is None
        or not notary_profile.strip()
        or release_readiness is None
        or validation_session is None
        or machine_acceptance is None
    ):
        raise ReleaseBuildError(
            "production builds require Developer ID identity, notary profile, "
            "release-readiness report, validation session, and machine acceptance"
        )


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise ReleaseBuildError("macOS release builds require macOS")


def _verify_release_readiness(
    *,
    report: Path,
    validation_session: Path,
    machine_acceptance: Path,
    source_revision: str,
) -> tuple[str, str, str]:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        result = run_verify_release_readiness(
            report_path=str(report),
            validation_session=str(validation_session),
            machine_acceptance=str(machine_acceptance),
            source_revision=source_revision,
            json_output=True,
        )
    if result != 0:
        raise ReleaseBuildError(
            "production release readiness verification did not qualify"
        )
    readiness = load_release_readiness_report(report)
    if not readiness.qualified_for_release:
        raise ReleaseBuildError(
            "production release readiness artifact is not qualified"
        )
    return (
        _sha256(report.expanduser().resolve(strict=True)),
        readiness.candidate_label,
        readiness.validated_profile_id,
    )


def _build_helper(
    *,
    destination: Path,
    mode: ReleaseBuildMode,
    identity: str | None,
) -> None:
    uv = _require_tool("uv")
    command = [
        uv,
        "run",
        "--with",
        f"pyinstaller=={_PYINSTALLER_VERSION}",
        "--with",
        f"pyinstaller-hooks-contrib=={_PYINSTALLER_HOOKS_VERSION}",
        "python",
        str(_HELPER_BUILD_SCRIPT),
        "build",
        "--output",
        str(destination),
        "--clean",
    ]
    if mode == "production":
        assert identity is not None
        command.extend(["--codesign-identity", identity])
    _run(command, cwd=_REPOSITORY_ROOT)


def _build_desktop() -> Path:
    swift = _require_tool("swift")
    _run(
        [swift, "build", "--package-path", str(_DESKTOP_PACKAGE), "-c", "release"],
        cwd=_REPOSITORY_ROOT,
    )
    bin_dir = Path(
        _capture(
            [
                swift,
                "build",
                "--package-path",
                str(_DESKTOP_PACKAGE),
                "-c",
                "release",
                "--show-bin-path",
            ],
            cwd=_REPOSITORY_ROOT,
        )
    )
    executable = bin_dir / "AllyDesktop"
    if not executable.is_file():
        raise ReleaseBuildError("Swift release build did not produce AllyDesktop")
    return executable


def _archive(app: Path, archive: Path) -> None:
    ditto = _require_tool("ditto")
    _run(
        [
            ditto,
            "-c",
            "-k",
            "--keepParent",
            str(app),
            str(archive),
        ]
    )


def _verify_archive(archive: Path) -> None:
    ditto = _require_tool("ditto")
    with tempfile.TemporaryDirectory(prefix="ally-release-archive-verify-") as temporary:
        root = Path(temporary)
        _run([ditto, "-x", "-k", str(archive), str(root)])
        extracted = root / "Ally.app"
        if not extracted.is_dir():
            raise ReleaseBuildError("release archive does not contain Ally.app")
        macos_app_bundle.verify(extracted)


def _prepare_destination(
    *,
    destination: Path,
    mode: ReleaseBuildMode,
    clean: bool,
) -> None:
    if not destination.exists() and not destination.is_symlink():
        destination.parent.mkdir(parents=True, exist_ok=True)
        return
    if mode == "production" or not clean:
        raise ReleaseBuildError("release output already exists")
    if destination.is_symlink():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)
    else:
        destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)


def build_release(
    *,
    mode: ReleaseBuildMode,
    source_revision: str,
    build_version: str,
    output_dir: Path,
    identity: str | None,
    notary_profile: str | None,
    release_readiness: Path | None,
    validation_session: Path | None,
    machine_acceptance: Path | None,
    clean: bool,
) -> Path:
    """Build, sign, verify, archive, and describe one local release artifact."""

    _require_source_revision(source_revision)
    _require_build_version(build_version)
    _require_request(
        mode=mode,
        identity=identity,
        notary_profile=notary_profile,
        release_readiness=release_readiness,
        validation_session=validation_session,
        machine_acceptance=machine_acceptance,
        clean=clean,
    )
    destination = _require_output_outside_repository(output_dir)
    _require_macos()
    _require_checkout(source_revision)

    for tool in ("swift", "uv", "codesign", "ditto"):
        _require_tool(tool)
    if mode == "production":
        for tool in ("xcrun", "spctl"):
            _require_tool(tool)

    readiness_sha256: str | None = None
    candidate_label: str | None = None
    validated_profile_id: str | None = None
    if mode == "production":
        assert release_readiness is not None
        assert validation_session is not None
        assert machine_acceptance is not None
        (
            readiness_sha256,
            candidate_label,
            validated_profile_id,
        ) = _verify_release_readiness(
            report=release_readiness,
            validation_session=validation_session,
            machine_acceptance=machine_acceptance,
            source_revision=source_revision,
        )

    _prepare_destination(destination=destination, mode=mode, clean=clean)
    temporary_root = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
    )
    staging = temporary_root / destination.name
    try:
        staging.mkdir()
        helper = staging / "ally-desktop-bridge"
        _build_helper(destination=helper, mode=mode, identity=identity)
        desktop = _build_desktop()

        app = staging / "Ally.app"
        macos_app_bundle.assemble(
            app_executable=desktop,
            helper=helper,
            output=app,
            source_revision=source_revision,
            build_version=build_version,
            replace=False,
        )

        if mode == "production":
            assert identity is not None
            assert notary_profile is not None
            macos_release_signing.sign(
                app,
                identity=identity,
                timestamp=True,
                dry_run=False,
            )
            macos_release_signing.notarize(
                app,
                keychain_profile=notary_profile,
                dry_run=False,
            )
        else:
            macos_release_signing.sign(
                app,
                identity="-",
                timestamp=False,
                dry_run=False,
            )

        manifest = macos_app_bundle.verify(app)
        archive = staging / "Ally.zip"
        _archive(app, archive)
        _verify_archive(archive)

        metadata = {
            "schema_version": 1,
            "ally_version": manifest["ally_version"],
            "bundle_identifier": manifest["bundle_identifier"],
            "build_version": manifest["build_version"],
            "bridge_protocol_version": manifest["bridge_protocol_version"],
            "database_schema_version": manifest["database_schema_version"],
            "source_revision": source_revision,
            "signing_mode": (
                "developer_id_notarized" if mode == "production" else "adhoc"
            ),
            "notarized": mode == "production",
            "archive_name": archive.name,
            "archive_sha256": _sha256(archive),
            "archive_size_bytes": archive.stat().st_size,
            "release_readiness_sha256": readiness_sha256,
            "candidate_label": candidate_label,
            "validated_profile_id": validated_profile_id,
        }
        (staging / "release-artifact.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except Exception:
        raise
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)

    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a local macOS Ally release artifact without publishing it."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--mode", choices=("adhoc", "production"), required=True)
    build_parser.add_argument("--source-revision", required=True)
    build_parser.add_argument("--build-version", required=True)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--identity")
    build_parser.add_argument("--notary-profile")
    build_parser.add_argument("--release-readiness", type=Path)
    build_parser.add_argument("--validation-session", type=Path)
    build_parser.add_argument("--machine-acceptance", type=Path)
    build_parser.add_argument("--clean", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        destination = build_release(
            mode=args.mode,
            source_revision=args.source_revision,
            build_version=args.build_version,
            output_dir=args.output_dir,
            identity=args.identity,
            notary_profile=args.notary_profile,
            release_readiness=args.release_readiness,
            validation_session=args.validation_session,
            machine_acceptance=args.machine_acceptance,
            clean=args.clean,
        )
        metadata = json.loads(
            (destination / "release-artifact.json").read_text(encoding="utf-8")
        )
        print(
            json.dumps(
                {
                    "output_dir": str(destination),
                    "app": str(destination / "Ally.app"),
                    "archive": str(destination / "Ally.zip"),
                    "metadata": metadata,
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        FileNotFoundError,
        OSError,
        ReleaseBuildError,
        macos_app_bundle.BundleError,
        macos_release_signing.SigningError,
        subprocess.CalledProcessError,
        ValueError,
    ) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
