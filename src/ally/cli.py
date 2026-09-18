"""Ally command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import cast

from ally import __version__
from ally.commands.chat import run_chat
from ally.commands.conversations import run_list_conversations, run_show_conversation
from ally.commands.doctor import run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ally",
        description="Local-first personal AI.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("doctor", help="Show local Ally environment information.")

    chat = subcommands.add_parser("chat", help="Chat with a local inference server.")
    chat.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1",
        help="OpenAI-compatible base URL. Defaults to local llama.cpp-style endpoint.",
    )
    chat.add_argument("--model", required=True, help="Model identifier exposed by the server.")
    chat.add_argument("--prompt", help="Run one prompt and exit instead of interactive chat.")
    chat.add_argument(
        "--conversation",
        help="Resume an existing conversation UUID instead of creating a new one.",
    )
    chat.add_argument(
        "--allow-remote",
        action="store_true",
        help="Explicitly allow a non-loopback inference endpoint.",
    )

    conversations = subcommands.add_parser(
        "conversations",
        help="Inspect locally stored conversations.",
    )
    conversation_commands = conversations.add_subparsers(dest="conversations_command")

    list_command = conversation_commands.add_parser("list", help="List recent conversations.")
    list_command.add_argument("--limit", type=int, default=20)

    show_command = conversation_commands.add_parser("show", help="Show one conversation.")
    show_command.add_argument("conversation_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()

    if args.command == "chat":
        return run_chat(
            endpoint=cast(str, args.endpoint),
            model=cast(str, args.model),
            prompt=cast(str | None, args.prompt),
            allow_remote=cast(bool, args.allow_remote),
            conversation_id=cast(str | None, args.conversation),
        )

    if args.command == "conversations":
        if args.conversations_command == "list":
            return run_list_conversations(limit=cast(int, args.limit))
        if args.conversations_command == "show":
            return run_show_conversation(
                conversation_id=cast(str, args.conversation_id)
            )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
