"""Initial Ally command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ally import __version__
from ally.config import default_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ally",
        description="Local-first personal AI.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("doctor", help="Show local Ally environment information.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        paths = default_paths()
        print(f"Ally {__version__}")
        print(f"Config: {paths.config_dir}")
        print(f"Data:   {paths.data_dir}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
