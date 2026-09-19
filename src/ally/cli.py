"""Ally command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import cast

from ally import __version__
from ally.attention import AttentionDeliveryStatus
from ally.commands.attention import (
    run_deliver_attention,
    run_list_attention_history,
    run_list_pending_attention,
)
from ally.commands.chat import run_chat
from ally.commands.configuration import (
    run_config_init,
    run_config_path,
    run_config_show,
    run_config_validate,
)
from ally.commands.conversations import run_list_conversations, run_show_conversation
from ally.commands.data import run_data_backup, run_restore_backup, run_validate_backup
from ally.commands.doctor import run_doctor
from ally.commands.evals import run_core_evals, run_provider_evals
from ally.commands.events import (
    run_emit_event,
    run_handle_event,
    run_list_events,
    run_show_event,
)
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
from ally.commands.memory_proposals import (
    run_accept_memory_proposals,
    run_propose_memories,
)
from ally.commands.planning import run_propose_plan
from ally.commands.service import run_proactive_cycle
from ally.commands.schedules import (
    run_create_schedule,
    run_list_schedules,
    run_set_schedule_enabled,
    run_show_schedule,
    run_tick_schedules,
)
from ally.commands.skills import (
    run_disable_skill,
    run_enable_skill,
    run_inspect_skill,
    run_install_skill,
    run_list_installed_skills,
    run_uninstall_skill,
    run_validate_skill,
)
from ally.commands.tasks import (
    run_create_task,
    run_list_tasks,
    run_retry_task_step,
    run_show_task,
    run_task,
)
from ally.commands.tools import run_list_tools, run_tool, run_tool_audit
from ally.commands.validate import (
    run_hardware_report,
    run_local_model_validation_command,
)
from ally.events import (
    ATTENTION_CLASSES,
    EVENT_IMPORTANCE_LEVELS,
    AttentionClass,
    EventImportance,
)
from ally.memory import (
    MEMORY_KINDS,
    MEMORY_PRIVACY_LEVELS,
    MEMORY_SOURCE_TYPES,
    MemoryKind,
    MemoryPrivacy,
    MemorySourceType,
)


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

    config = subcommands.add_parser(
        "config",
        help="Inspect Ally's non-secret versioned configuration.",
    )
    config_commands = config.add_subparsers(dest="config_command")
    config_commands.add_parser("path", help="Show the Ally config file path.")
    config_commands.add_parser(
        "init",
        help="Create the default config without overwriting an existing file.",
    )
    config_commands.add_parser(
        "show",
        help="Show current config or safe defaults without writing a file.",
    )
    config_commands.add_parser(
        "validate",
        help="Validate the existing config file.",
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

    memory_propose = memory_commands.add_parser(
        "propose",
        help="Ask a model for reviewable memory candidates without storing them.",
    )
    memory_propose.add_argument("text")
    memory_propose.add_argument("--model", required=True)
    memory_propose.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1",
    )
    memory_propose.add_argument("--allow-remote", action="store_true")
    memory_propose.add_argument(
        "--source-type",
        choices=MEMORY_SOURCE_TYPES,
        default="user",
    )
    memory_propose.add_argument("--source-id")
    memory_propose.add_argument("--source-uri")
    memory_propose.add_argument(
        "--privacy",
        choices=MEMORY_PRIVACY_LEVELS,
        default="private",
    )
    memory_propose.add_argument(
        "--output",
        help="Optional JSON file for later review/acceptance.",
    )

    memory_accept = memory_commands.add_parser(
        "accept",
        help="Store explicitly selected candidates from a proposal JSON file.",
    )
    memory_accept.add_argument("proposal_path")
    memory_accept.add_argument(
        "--index",
        type=int,
        action="append",
        default=[],
        dest="indices",
        help="Proposal index to accept; may be repeated.",
    )

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

    data = subcommands.add_parser(
        "data",
        help="Back up, validate, and restore user-owned Ally state.",
    )
    data_commands = data.add_subparsers(dest="data_command")

    data_backup = data_commands.add_parser(
        "backup",
        help="Create a versioned Ally database archive.",
    )
    data_backup.add_argument("output")

    data_validate = data_commands.add_parser(
        "validate",
        help="Validate an Ally backup archive.",
    )
    data_validate.add_argument("archive")

    data_restore = data_commands.add_parser(
        "restore",
        help="Restore into a database path that does not already exist.",
    )
    data_restore.add_argument("archive")
    data_restore.add_argument(
        "--destination",
        help="Optional database path; defaults to Ally's normal local database.",
    )

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

    tools = subcommands.add_parser(
        "tools",
        help="Inspect and invoke permissioned Ally tools.",
    )
    tool_commands = tools.add_subparsers(dest="tools_command")

    tool_commands.add_parser("list", help="List registered tools.")

    tool_run = tool_commands.add_parser("run", help="Invoke a registered tool.")
    tool_run.add_argument("name")
    tool_run.add_argument(
        "--arguments",
        default="{}",
        help="Tool arguments as a JSON object.",
    )
    tool_run.add_argument(
        "--approved",
        action="store_true",
        help="Record explicit approval for tools whose policy requires it.",
    )

    tool_audit = tool_commands.add_parser("audit", help="Show recent tool audit records.")
    tool_audit.add_argument("--limit", type=int, default=20)

    tasks = subcommands.add_parser(
        "tasks",
        help="Create, inspect, and advance persistent Ally tasks.",
    )
    task_commands = tasks.add_subparsers(dest="tasks_command")

    task_create = task_commands.add_parser(
        "create",
        help="Create a task from a JSON TaskPlan file.",
    )
    task_create.add_argument("plan_path")

    task_list = task_commands.add_parser("list", help="List recent tasks.")
    task_list.add_argument("--limit", type=int, default=20)

    task_show = task_commands.add_parser("show", help="Show one task and its steps.")
    task_show.add_argument("task_id")

    task_run = task_commands.add_parser(
        "run",
        help="Advance a task until completion, failure, or required approval.",
    )
    task_run.add_argument("task_id")
    task_run.add_argument(
        "--approve-step",
        action="append",
        default=[],
        dest="approved_steps",
        help="Explicitly approve a waiting step UUID; may be repeated.",
    )

    task_retry = task_commands.add_parser(
        "retry",
        help="Reset one failed step to pending.",
    )
    task_retry.add_argument("task_id")
    task_retry.add_argument("step_id")

    attention = subcommands.add_parser(
        "attention",
        help="Inspect and deliver pending proactive attention.",
    )
    attention_commands = attention.add_subparsers(dest="attention_command")

    attention_pending = attention_commands.add_parser(
        "pending",
        help="List unhandled user-facing attention events.",
    )
    attention_pending.add_argument("--limit", type=int, default=50)

    attention_deliver = attention_commands.add_parser(
        "deliver",
        help="Deliver pending attention through an explicit sink.",
    )
    attention_deliver.add_argument(
        "--sink",
        choices=("console",),
        default="console",
    )
    attention_deliver.add_argument("--limit", type=int, default=50)

    attention_history = attention_commands.add_parser(
        "history",
        help="List durable attention delivery attempts.",
    )
    attention_history.add_argument("--limit", type=int, default=50)
    attention_history.add_argument(
        "--status",
        choices=("succeeded", "failed"),
    )

    events = subcommands.add_parser(
        "events",
        help="Inspect and emit persisted proactive events.",
    )
    event_commands = events.add_subparsers(dest="events_command")

    event_emit = event_commands.add_parser(
        "emit",
        help="Persist one explicit event and classify its attention.",
    )
    event_emit.add_argument("event_type")
    event_emit.add_argument("--source", default="cli")
    event_emit.add_argument(
        "--importance",
        choices=EVENT_IMPORTANCE_LEVELS,
        default="routine",
    )
    event_emit.add_argument(
        "--payload",
        default="{}",
        help="Event payload as a JSON object.",
    )

    event_list = event_commands.add_parser("list", help="List recent events.")
    event_list.add_argument("--limit", type=int, default=50)
    event_list.add_argument("--attention", choices=ATTENTION_CLASSES)
    handled_group = event_list.add_mutually_exclusive_group()
    handled_group.add_argument(
        "--handled",
        action="store_const",
        const=True,
        dest="handled",
    )
    handled_group.add_argument(
        "--pending",
        action="store_const",
        const=False,
        dest="handled",
    )

    event_show = event_commands.add_parser("show", help="Show one event.")
    event_show.add_argument("event_id")

    event_handle = event_commands.add_parser(
        "handle",
        help="Mark an event as handled.",
    )
    event_handle.add_argument("event_id")

    service = subcommands.add_parser(
        "service",
        help="Run bounded service operations without starting a daemon.",
    )
    service_commands = service.add_subparsers(dest="service_command")
    service_cycle = service_commands.add_parser(
        "cycle",
        help="Run one proactive schedule-and-attention cycle.",
    )
    service_cycle.add_argument(
        "--at",
        help="Optional timezone-aware ISO-8601 evaluation time.",
    )
    service_cycle.add_argument(
        "--schedule-limit",
        type=int,
        default=100,
    )
    service_cycle.add_argument(
        "--delivery-limit",
        type=int,
        default=50,
    )
    service_cycle.add_argument(
        "--sink",
        choices=("console",),
        default="console",
    )
    service_cycle.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

    schedules = subcommands.add_parser(
        "schedules",
        help="Create and advance persisted time-based event schedules.",
    )
    schedule_commands = schedules.add_subparsers(dest="schedules_command")

    schedule_create = schedule_commands.add_parser(
        "create",
        help="Create a one-shot or fixed-interval schedule.",
    )
    schedule_create.add_argument("--name", required=True)
    schedule_create.add_argument("--event-type", required=True)
    schedule_create.add_argument(
        "--at",
        required=True,
        help="Timezone-aware ISO-8601 first-run timestamp.",
    )
    schedule_create.add_argument(
        "--every-seconds",
        type=int,
        help="Optional fixed recurrence interval in seconds.",
    )
    schedule_create.add_argument(
        "--importance",
        choices=EVENT_IMPORTANCE_LEVELS,
        default="routine",
    )
    schedule_create.add_argument(
        "--payload",
        default="{}",
        help="Event data as a JSON object.",
    )
    schedule_create.add_argument(
        "--disabled",
        action="store_true",
        help="Create the schedule disabled.",
    )

    schedule_list = schedule_commands.add_parser(
        "list",
        help="List persisted schedules.",
    )
    schedule_list.add_argument("--limit", type=int, default=50)

    schedule_show = schedule_commands.add_parser(
        "show",
        help="Show one persisted schedule.",
    )
    schedule_show.add_argument("schedule_id")

    schedule_enable = schedule_commands.add_parser(
        "enable",
        help="Enable an incomplete schedule.",
    )
    schedule_enable.add_argument("schedule_id")

    schedule_disable = schedule_commands.add_parser(
        "disable",
        help="Disable a schedule.",
    )
    schedule_disable.add_argument("schedule_id")

    schedule_tick = schedule_commands.add_parser(
        "tick",
        help="Emit events for schedules due at an explicit/current time.",
    )
    schedule_tick.add_argument(
        "--at",
        help="Optional timezone-aware ISO-8601 evaluation time.",
    )
    schedule_tick.add_argument("--limit", type=int, default=100)

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

    skill_install = skill_commands.add_parser(
        "install",
        help="Copy a validated local skill package into Ally-owned storage.",
    )
    skill_install.add_argument("path")

    skill_commands.add_parser(
        "installed",
        help="List locally installed skill versions.",
    )

    skill_enable = skill_commands.add_parser(
        "enable",
        help="Enable one installed skill version.",
    )
    skill_enable.add_argument("skill_id")
    skill_enable.add_argument("version")

    skill_disable = skill_commands.add_parser(
        "disable",
        help="Disable one installed skill version.",
    )
    skill_disable.add_argument("skill_id")
    skill_disable.add_argument("version")

    skill_uninstall = skill_commands.add_parser(
        "uninstall",
        help="Remove one Ally-owned installed skill version.",
    )
    skill_uninstall.add_argument("skill_id")
    skill_uninstall.add_argument("version")

    validate = subcommands.add_parser(
        "validate",
        help="Run reproducible machine and local-model validation.",
    )
    validate_commands = validate.add_subparsers(dest="validate_command")

    validate_hardware = validate_commands.add_parser(
        "hardware",
        help="Print the non-sensitive local hardware profile.",
    )
    validate_hardware.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

    validate_model = validate_commands.add_parser(
        "local-model",
        help="Run frozen Ally checks against a loopback model server.",
    )
    validate_model.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1",
    )
    validate_model.add_argument("--model", required=True)
    validate_model.add_argument(
        "--core-cases",
        default="evals/cases/core.jsonl",
    )
    validate_model.add_argument(
        "--provider-cases",
        default="evals/cases/provider-smoke.jsonl",
    )
    validate_model.add_argument(
        "--output",
        default="validation/ally-local-model.json",
    )

    plan = subcommands.add_parser(
        "plan",
        help="Ask a model to propose TaskPlan data without executing it.",
    )
    plan_commands = plan.add_subparsers(dest="plan_command")
    plan_propose = plan_commands.add_parser(
        "propose",
        help="Print a validated non-executing task-plan proposal.",
    )
    plan_propose.add_argument("--goal", required=True)
    plan_propose.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1",
    )
    plan_propose.add_argument("--model", required=True)
    plan_propose.add_argument(
        "--allow-remote",
        action="store_true",
        help="Explicitly allow a non-loopback inference endpoint.",
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

    if args.command == "config":
        if args.config_command == "path":
            return run_config_path()
        if args.config_command == "init":
            return run_config_init()
        if args.config_command == "show":
            return run_config_show()
        if args.config_command == "validate":
            return run_config_validate()

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
        if args.memory_command == "propose":
            return run_propose_memories(
                endpoint=cast(str, args.endpoint),
                model=cast(str, args.model),
                text=cast(str, args.text),
                source_type=cast(MemorySourceType, args.source_type),
                source_id=cast(str | None, args.source_id),
                source_uri=cast(str | None, args.source_uri),
                privacy=cast(MemoryPrivacy, args.privacy),
                allow_remote=cast(bool, args.allow_remote),
                output=cast(str | None, args.output),
            )
        if args.memory_command == "accept":
            return run_accept_memory_proposals(
                proposal_path=cast(str, args.proposal_path),
                indices=tuple(cast(list[int], args.indices)),
            )

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

    if args.command == "data":
        if args.data_command == "backup":
            return run_data_backup(output=cast(str, args.output))
        if args.data_command == "validate":
            return run_validate_backup(archive=cast(str, args.archive))
        if args.data_command == "restore":
            return run_restore_backup(
                archive=cast(str, args.archive),
                destination=cast(str | None, args.destination),
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

    if args.command == "tools":
        if args.tools_command == "list":
            return run_list_tools()
        if args.tools_command == "run":
            return run_tool(
                name=cast(str, args.name),
                arguments_json=cast(str, args.arguments),
                approved=cast(bool, args.approved),
            )
        if args.tools_command == "audit":
            return run_tool_audit(limit=cast(int, args.limit))

    if args.command == "tasks":
        if args.tasks_command == "create":
            return run_create_task(plan_path=cast(str, args.plan_path))
        if args.tasks_command == "list":
            return run_list_tasks(limit=cast(int, args.limit))
        if args.tasks_command == "show":
            return run_show_task(task_id=cast(str, args.task_id))
        if args.tasks_command == "run":
            return run_task(
                task_id=cast(str, args.task_id),
                approved_steps=tuple(cast(list[str], args.approved_steps)),
            )
        if args.tasks_command == "retry":
            return run_retry_task_step(
                task_id=cast(str, args.task_id),
                step_id=cast(str, args.step_id),
            )

    if args.command == "attention":
        if args.attention_command == "pending":
            return run_list_pending_attention(limit=cast(int, args.limit))
        if args.attention_command == "deliver":
            return run_deliver_attention(
                sink_name=cast(str, args.sink),
                limit=cast(int, args.limit),
            )
        if args.attention_command == "history":
            return run_list_attention_history(
                limit=cast(int, args.limit),
                status=cast(AttentionDeliveryStatus | None, args.status),
            )

    if args.command == "events":
        if args.events_command == "emit":
            return run_emit_event(
                event_type=cast(str, args.event_type),
                source=cast(str, args.source),
                importance=cast(EventImportance, args.importance),
                payload_json=cast(str, args.payload),
            )
        if args.events_command == "list":
            return run_list_events(
                limit=cast(int, args.limit),
                attention=cast(AttentionClass | None, args.attention),
                handled=cast(bool | None, args.handled),
            )
        if args.events_command == "show":
            return run_show_event(event_id=cast(str, args.event_id))
        if args.events_command == "handle":
            return run_handle_event(event_id=cast(str, args.event_id))

    if args.command == "service" and args.service_command == "cycle":
        return run_proactive_cycle(
            at=cast(str | None, args.at),
            schedule_limit=cast(int, args.schedule_limit),
            delivery_limit=cast(int, args.delivery_limit),
            sink_name=cast(str, args.sink),
            json_output=cast(bool, args.json_output),
        )

    if args.command == "schedules":
        if args.schedules_command == "create":
            return run_create_schedule(
                name=cast(str, args.name),
                event_type=cast(str, args.event_type),
                at=cast(str, args.at),
                every_seconds=cast(int | None, args.every_seconds),
                importance=cast(EventImportance, args.importance),
                payload_json=cast(str, args.payload),
                disabled=cast(bool, args.disabled),
            )
        if args.schedules_command == "list":
            return run_list_schedules(limit=cast(int, args.limit))
        if args.schedules_command == "show":
            return run_show_schedule(schedule_id=cast(str, args.schedule_id))
        if args.schedules_command == "enable":
            return run_set_schedule_enabled(
                schedule_id=cast(str, args.schedule_id),
                enabled=True,
            )
        if args.schedules_command == "disable":
            return run_set_schedule_enabled(
                schedule_id=cast(str, args.schedule_id),
                enabled=False,
            )
        if args.schedules_command == "tick":
            return run_tick_schedules(
                at=cast(str | None, args.at),
                limit=cast(int, args.limit),
            )

    if args.command == "skills":
        if args.skills_command == "inspect":
            return run_inspect_skill(path=cast(str, args.path))
        if args.skills_command == "validate":
            return run_validate_skill(
                path=cast(str, args.path),
                available_tools=tuple(cast(list[str], args.available_tools)),
            )
        if args.skills_command == "install":
            return run_install_skill(path=cast(str, args.path))
        if args.skills_command == "installed":
            return run_list_installed_skills()
        if args.skills_command == "enable":
            return run_enable_skill(
                skill_id=cast(str, args.skill_id),
                version=cast(str, args.version),
            )
        if args.skills_command == "disable":
            return run_disable_skill(
                skill_id=cast(str, args.skill_id),
                version=cast(str, args.version),
            )
        if args.skills_command == "uninstall":
            return run_uninstall_skill(
                skill_id=cast(str, args.skill_id),
                version=cast(str, args.version),
            )

    if args.command == "validate":
        if args.validate_command == "hardware":
            return run_hardware_report(json_output=cast(bool, args.json_output))
        if args.validate_command == "local-model":
            return run_local_model_validation_command(
                endpoint=cast(str, args.endpoint),
                model=cast(str, args.model),
                core_case_file=cast(str, args.core_cases),
                provider_case_file=cast(str, args.provider_cases),
                output=cast(str, args.output),
            )

    if args.command == "plan" and args.plan_command == "propose":
        return run_propose_plan(
            endpoint=cast(str, args.endpoint),
            model=cast(str, args.model),
            goal=cast(str, args.goal),
            allow_remote=cast(bool, args.allow_remote),
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
