"""Ally command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import cast

from ally import __version__
from ally.commands.chat import run_chat
from ally.commands.conversations import run_list_conversations, run_show_conversation
from ally.commands.doctor import run_doctor
from ally.commands.evals import run_core_evals, run_provider_evals
from ally.commands.knowledge import (
    run_ingest_knowledge_file,
    run_list_knowledge_sources,
    run_search_knowledge,
    run_show_knowledge_source,
)
from ally.commands.memory import (
    run_list_memories,
    run_remember,
    run_retract_memory,
    run_search_memories,
    run_show_memory,
    run_supersede_memory,
)
from ally.commands.skills import run_inspect_skill, run_validate_skill
from ally.memory import MEMORY_KINDS, MEMORY_PRIVACY_LEVELS, MemoryKind, MemoryPrivacy


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
    chat.add_argument(
        "--allow-private-context-remote",
        action="store_true",
        help="Allow memory/document grounding to be sent to a remote endpoint.",
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

    memory = subcommands.add_parser("memory", help="Inspect and correct Ally memory.")
    memory_commands = memory.add_subparsers(dest="memory_command")

    remember = memory_commands.add_parser("remember", help="Store an explicit memory.")
    remember.add_argument("content")
    remember.add_argument("--kind", choices=MEMORY_KINDS, default="semantic")
    remember.add_argument("--confidence", type=float, default=1.0)
    remember.add_argument("--importance", type=float, default=0.5)
    remember.add_argument(
        "--privacy",
        choices=MEMORY_PRIVACY_LEVELS,
        default="private",
    )

    memory_list = memory_commands.add_parser("list", help="List memories.")
    memory_list.add_argument("--kind", choices=MEMORY_KINDS)
    memory_list.add_argument("--all", action="store_true", dest="include_inactive")
    memory_list.add_argument("--limit", type=int, default=50)

    memory_search = memory_commands.add_parser("search", help="Search memory text.")
    memory_search.add_argument("query")
    memory_search.add_argument("--limit", type=int, default=20)

    memory_show = memory_commands.add_parser("show", help="Show one memory.")
    memory_show.add_argument("memory_id")

    memory_supersede = memory_commands.add_parser(
        "supersede",
        help="Replace a memory while preserving its history.",
    )
    memory_supersede.add_argument("memory_id")
    memory_supersede.add_argument("content")

    memory_retract = memory_commands.add_parser("retract", help="Retract a memory.")
    memory_retract.add_argument("memory_id")

    knowledge = subcommands.add_parser(
        "knowledge",
        help="Ingest and inspect personal knowledge.",
    )
    knowledge_commands = knowledge.add_subparsers(dest="knowledge_command")

    knowledge_ingest = knowledge_commands.add_parser(
        "ingest",
        help="Ingest a UTF-8 plain-text file.",
    )
    knowledge_ingest.add_argument("path")

    knowledge_list = knowledge_commands.add_parser("list", help="List knowledge sources.")
    knowledge_list.add_argument("--limit", type=int, default=50)

    knowledge_show = knowledge_commands.add_parser(
        "show",
        help="Show a knowledge source and revision history.",
    )
    knowledge_show.add_argument("source_id")

    knowledge_search = knowledge_commands.add_parser(
        "search",
        help="Search current knowledge chunks.",
    )
    knowledge_search.add_argument("query")
    knowledge_search.add_argument("--limit", type=int, default=8)

    eval_command = subcommands.add_parser(
        "eval",
        help="Run Ally behavioral evaluations.",
    )
    eval_commands = eval_command.add_subparsers(dest="eval_command")

    eval_run = eval_commands.add_parser(
        "run",
        help="Run deterministic evaluations that require no model.",
    )
    eval_run.add_argument("case_file")
    eval_run.add_argument("--json", action="store_true", dest="json_output")

    eval_provider = eval_commands.add_parser(
        "provider",
        help="Run model-provider smoke evaluations.",
    )
    eval_provider.add_argument("case_file")
    eval_provider.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1",
    )
    eval_provider.add_argument("--model", required=True)
    eval_provider.add_argument("--allow-remote", action="store_true")
    eval_provider.add_argument("--json", action="store_true", dest="json_output")

    skills = subcommands.add_parser(
        "skills",
        help="Inspect and validate Ally skill packages.",
    )
    skill_commands = skills.add_subparsers(dest="skills_command")

    skill_inspect = skill_commands.add_parser(
        "inspect",
        help="Inspect a skill.toml package without executing it.",
    )
    skill_inspect.add_argument("path")

    skill_validate = skill_commands.add_parser(
        "validate",
        help="Validate a skill manifest and its required tool names.",
    )
    skill_validate.add_argument("path")
    skill_validate.add_argument(
        "--available-tool",
        action="append",
        default=[],
        dest="available_tools",
        help="Tool name available to the target runtime; may be repeated.",
    )

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
            allow_private_context_remote=cast(
                bool,
                args.allow_private_context_remote,
            ),
            conversation_id=cast(str | None, args.conversation),
        )

    if args.command == "conversations":
        if args.conversations_command == "list":
            return run_list_conversations(limit=cast(int, args.limit))
        if args.conversations_command == "show":
            return run_show_conversation(
                conversation_id=cast(str, args.conversation_id)
            )

    if args.command == "memory":
        if args.memory_command == "remember":
            return run_remember(
                content=cast(str, args.content),
                kind=cast(MemoryKind, args.kind),
                confidence=cast(float, args.confidence),
                importance=cast(float, args.importance),
                privacy=cast(MemoryPrivacy, args.privacy),
            )
        if args.memory_command == "list":
            return run_list_memories(
                kind=cast(MemoryKind | None, args.kind),
                include_inactive=cast(bool, args.include_inactive),
                limit=cast(int, args.limit),
            )
        if args.memory_command == "search":
            return run_search_memories(
                query=cast(str, args.query),
                limit=cast(int, args.limit),
            )
        if args.memory_command == "show":
            return run_show_memory(memory_id=cast(str, args.memory_id))
        if args.memory_command == "supersede":
            return run_supersede_memory(
                memory_id=cast(str, args.memory_id),
                content=cast(str, args.content),
            )
        if args.memory_command == "retract":
            return run_retract_memory(memory_id=cast(str, args.memory_id))

    if args.command == "knowledge":
        if args.knowledge_command == "ingest":
            return run_ingest_knowledge_file(path=cast(str, args.path))
        if args.knowledge_command == "list":
            return run_list_knowledge_sources(limit=cast(int, args.limit))
        if args.knowledge_command == "show":
            return run_show_knowledge_source(source_id=cast(str, args.source_id))
        if args.knowledge_command == "search":
            return run_search_knowledge(
                query=cast(str, args.query),
                limit=cast(int, args.limit),
            )

    if args.command == "eval":
        if args.eval_command == "run":
            return run_core_evals(
                case_file=cast(str, args.case_file),
                json_output=cast(bool, args.json_output),
            )
        if args.eval_command == "provider":
            return run_provider_evals(
                case_file=cast(str, args.case_file),
                endpoint=cast(str, args.endpoint),
                model=cast(str, args.model),
                allow_remote=cast(bool, args.allow_remote),
                json_output=cast(bool, args.json_output),
            )

    if args.command == "skills":
        if args.skills_command == "inspect":
            return run_inspect_skill(path=cast(str, args.path))
        if args.skills_command == "validate":
            return run_validate_skill(
                path=cast(str, args.path),
                available_tools=tuple(cast(list[str], args.available_tools)),
            )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
