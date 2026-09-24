"""Ally command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import cast

from ally import __version__
from ally.attention import AttentionDeliveryStatus, AttentionSinkName
from ally.commands.attention import (
    run_attention_sink_health,
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
from ally.commands.evals import run_behavior_evals, run_core_evals, run_provider_evals
from ally.commands.events import (
    run_emit_event,
    run_handle_event,
    run_list_events,
    run_show_event,
)
from ally.commands.instructions import (
    run_clear_instructions,
    run_list_instructions,
    run_resolve_instructions,
    run_set_instructions,
    run_set_instructions_enabled,
    run_show_instructions,
)
from ally.commands.knowledge import (
    run_ingest_knowledge_file,
    run_list_knowledge_sources,
    run_search_knowledge,
    run_show_knowledge_source,
)
from ally.commands.managed_service import run_managed_service
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
from ally.commands.schedules import (
    run_create_schedule,
    run_list_schedules,
    run_set_schedule_enabled,
    run_show_schedule,
    run_tick_schedules,
)
from ally.commands.secrets import (
    run_check_secret,
    run_delete_secret,
    run_list_secret_references,
    run_set_secret,
)
from ally.commands.service import (
    run_list_service_leases,
    run_proactive_cycle,
    run_service_health,
    run_service_history,
)
from ally.commands.skills import (
    run_disable_skill,
    run_enable_skill,
    run_execute_skill,
    run_inspect_skill,
    run_install_skill,
    run_list_installed_skills,
    run_skill_execution_audit,
    run_uninstall_skill,
    run_validate_skill,
)
from ally.commands.sources import (
    run_list_source_checkpoints,
    run_poll_filesystem_source,
    run_poll_jsonl_source,
    run_show_source_checkpoint,
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
    run_compare_validation_reports,
    run_hardware_report,
    run_local_model_validation_command,
)
from ally.events import (
    ATTENTION_CLASSES,
    EVENT_IMPORTANCE_LEVELS,
    AttentionClass,
    EventImportance,
)
from ally.instructions import INSTRUCTION_SCOPES, InstructionScope
from ally.memory import (
    MEMORY_KINDS,
    MEMORY_PRIVACY_LEVELS,
    MEMORY_SOURCE_TYPES,
    MemoryKind,
    MemoryPrivacy,
    MemorySourceType,
)
from ally.storage.errors import DatabaseMigrationError


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
        "--instruction-project",
        help="Optional project instruction-scope key for this chat.",
    )
    chat.add_argument(
        "--instruction-task",
        help="Optional task instruction-scope key for this chat.",
    )
    chat.add_argument(
        "--session-instructions",
        help="Temporary instructions for this invocation; never persisted.",
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

    instructions = subcommands.add_parser(
        "instructions",
        help="Inspect or change private scoped user instructions.",
    )
    instruction_commands = instructions.add_subparsers(dest="instructions_command")

    instruction_show = instruction_commands.add_parser(
        "show",
        help="Show one instruction profile.",
    )
    instruction_show.add_argument("--scope", choices=INSTRUCTION_SCOPES, default="global")
    instruction_show.add_argument("--key")

    instruction_set = instruction_commands.add_parser(
        "set",
        help="Create or replace one instruction profile.",
    )
    instruction_set.add_argument("content")
    instruction_set.add_argument("--scope", choices=INSTRUCTION_SCOPES, default="global")
    instruction_set.add_argument("--key")
    instruction_set.add_argument(
        "--disabled",
        action="store_true",
        help="Store the profile disabled.",
    )

    instruction_clear = instruction_commands.add_parser(
        "clear",
        help="Remove one instruction profile.",
    )
    instruction_clear.add_argument("--scope", choices=INSTRUCTION_SCOPES, default="global")
    instruction_clear.add_argument("--key")

    instruction_list = instruction_commands.add_parser(
        "list",
        help="List durable instruction profiles.",
    )
    instruction_list.add_argument(
        "--enabled-only",
        action="store_true",
        help="Hide disabled profiles.",
    )

    for action in ("enable", "disable"):
        instruction_toggle = instruction_commands.add_parser(
            action,
            help=f"{action.capitalize()} one durable instruction profile.",
        )
        instruction_toggle.add_argument(
            "--scope",
            choices=INSTRUCTION_SCOPES,
            default="global",
        )
        instruction_toggle.add_argument("--key")

    instruction_resolve = instruction_commands.add_parser(
        "resolve",
        help="Show exactly which instructions resolve for a synthetic context.",
    )
    instruction_resolve.add_argument("--project")
    instruction_resolve.add_argument("--conversation")
    instruction_resolve.add_argument("--task")
    instruction_resolve.add_argument(
        "--session",
        help="Optional temporary session instructions; never persisted.",
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

    secrets = subcommands.add_parser(
        "secrets",
        help="Manage opaque references in the operating-system secret store.",
    )
    secret_commands = secrets.add_subparsers(dest="secrets_command")

    secret_set = secret_commands.add_parser(
        "set",
        help="Prompt securely and store a secret value by opaque reference.",
    )
    secret_set.add_argument("name")

    secret_commands.add_parser(
        "list",
        help="List opaque secret references without reading their values.",
    )

    secret_check = secret_commands.add_parser(
        "check",
        help="Report whether one secret reference is available.",
    )
    secret_check.add_argument("name")

    secret_delete = secret_commands.add_parser(
        "delete",
        help="Delete one secret value and its opaque reference.",
    )
    secret_delete.add_argument("name")

    eval_command = subcommands.add_parser(
        "eval",
        help="Run Ally behavioral evaluations.",
    )
    eval_commands = eval_command.add_subparsers(dest="eval_command")

    eval_run = eval_commands.add_parser(
        "run",
        help="Run deterministic evaluations that require no model.",
    )
    eval_run.add_argument("case_file", nargs="?", help="Override the bundled core suite.")
    eval_run.add_argument("--json", action="store_true", dest="json_output")

    eval_provider = eval_commands.add_parser(
        "provider",
        help="Run model-provider smoke evaluations.",
    )
    eval_provider.add_argument(
        "case_file", nargs="?", help="Override the bundled provider smoke suite."
    )
    eval_provider.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1",
    )
    eval_provider.add_argument("--model", required=True)
    eval_provider.add_argument(
        "--allow-remote-public",
        action="store_true",
        help="Allow remote inference only for Ally's bundled synthetic/public suite.",
    )
    eval_provider.add_argument("--json", action="store_true", dest="json_output")

    eval_behavior = eval_commands.add_parser(
        "behavior",
        help="Run behavioral model qualification.",
    )
    eval_behavior.add_argument(
        "case_file",
        nargs="?",
        help="Override the bundled behavioral qualification suite.",
    )
    eval_behavior.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8080/v1",
    )
    eval_behavior.add_argument("--model", required=True)
    eval_behavior.add_argument(
        "--allow-remote-public",
        action="store_true",
        help="Allow remote inference only for Ally's bundled synthetic/public suite.",
    )
    eval_behavior.add_argument("--json", action="store_true", dest="json_output")

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
        choices=("auto", "console", "macos"),
        default="console",
    )
    attention_deliver.add_argument("--limit", type=int, default=50)

    attention_health = attention_commands.add_parser(
        "health",
        help="Inspect payload-free readiness for an attention sink.",
    )
    attention_health.add_argument(
        "--sink",
        choices=("auto", "console", "macos"),
        default="auto",
    )
    attention_health.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

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
        choices=("auto", "console", "macos"),
        default="auto",
    )
    service_cycle.add_argument(
        "--lease-seconds",
        type=int,
        default=300,
        help="Ephemeral overlap-protection lease duration.",
    )
    service_cycle.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )
    service_commands.add_parser(
        "leases",
        help="Inspect ephemeral runtime service leases.",
    )

    service_history = service_commands.add_parser(
        "history",
        help="Inspect portable proactive service lifecycle history.",
    )
    service_history.add_argument("--limit", type=int, default=50)
    service_history.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

    service_health = service_commands.add_parser(
        "health",
        help="Inspect durable state and ephemeral coordination health.",
    )
    service_health.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

    managed_service = service_commands.add_parser(
        "managed",
        help="Inspect or manage the opt-in macOS launch agent.",
    )
    managed_commands = managed_service.add_subparsers(dest="managed_service_command")
    managed_commands.add_parser(
        "inspect",
        help="Print the deterministic launch-agent definition without installing it.",
    )
    for action in ("status", "install", "start", "stop", "uninstall"):
        managed_action = managed_commands.add_parser(
            action,
            help=f"{action.capitalize()} the macOS launch agent.",
        )
        managed_action.add_argument("--json", action="store_true", dest="json_output")

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

    sources = subcommands.add_parser(
        "sources",
        help="Poll and inspect external event-source checkpoints.",
    )
    source_commands = sources.add_subparsers(dest="sources_command")

    source_poll_jsonl = source_commands.add_parser(
        "poll-jsonl",
        help="Poll an explicit local JSONL reference event source.",
    )
    source_poll_jsonl.add_argument("--source-id", required=True)
    source_poll_jsonl.add_argument("path")
    source_poll_jsonl.add_argument("--limit", type=int, default=100)
    source_poll_jsonl.add_argument(
        "--at",
        help="Optional timezone-aware ISO-8601 poll timestamp.",
    )
    source_poll_jsonl.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

    source_poll_filesystem = source_commands.add_parser(
        "poll-filesystem",
        help="Poll metadata below an explicit local directory without reading contents.",
    )
    source_poll_filesystem.add_argument("--source-id", required=True)
    source_poll_filesystem.add_argument("root")
    source_poll_filesystem.add_argument("--limit", type=int, default=100)
    source_poll_filesystem.add_argument("--max-entries", type=int, default=1000)
    source_poll_filesystem.add_argument("--include-hidden", action="store_true")
    source_poll_filesystem.add_argument(
        "--importance",
        choices=EVENT_IMPORTANCE_LEVELS,
        default="routine",
    )
    source_poll_filesystem.add_argument(
        "--at",
        help="Optional timezone-aware ISO-8601 poll timestamp.",
    )
    source_poll_filesystem.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
    )

    source_checkpoints = source_commands.add_parser(
        "checkpoints",
        help="List successful event-source checkpoints.",
    )
    source_checkpoints.add_argument("--limit", type=int, default=50)

    source_checkpoint = source_commands.add_parser(
        "checkpoint",
        help="Show one event-source checkpoint.",
    )
    source_checkpoint.add_argument("source_id")

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

    skill_run = skill_commands.add_parser(
        "run",
        help="Execute one enabled skill in a bounded child process.",
    )
    skill_run.add_argument("skill_id")
    skill_run.add_argument("version")
    skill_run.add_argument(
        "--input",
        default="{}",
        help="Explicit skill input as a JSON object.",
    )
    skill_run.add_argument(
        "--timeout-seconds",
        type=int,
        default=5,
    )

    skill_audit = skill_commands.add_parser(
        "audit",
        help="Inspect payload-free skill execution audit records.",
    )
    skill_audit.add_argument("--limit", type=int, default=50)

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
        "--runtime",
        required=True,
        help="Runtime name, such as llama.cpp or MLX LM.",
    )
    validate_model.add_argument(
        "--runtime-version",
        required=True,
        help="Exact runtime version used for this evidence.",
    )
    validate_model.add_argument("--model-source")
    validate_model.add_argument("--quantization")
    validate_model.add_argument("--precision")
    validate_model.add_argument("--model-size-bytes", type=int)
    validate_model.add_argument("--context-length", type=int)
    validate_model.add_argument(
        "--runtime-parameter",
        action="append",
        default=[],
        dest="runtime_parameters",
        metavar="NAME=VALUE",
        help="Record one explicit non-secret runtime setting; repeat as needed.",
    )
    validate_model.add_argument("--model-load-ms", type=float)
    validate_model.add_argument("--time-to-first-token-ms", type=float)
    validate_model.add_argument("--prompt-tokens-per-second", type=float)
    validate_model.add_argument("--generation-tokens-per-second", type=float)
    validate_model.add_argument("--peak-memory-bytes", type=int)
    validate_model.add_argument("--maximum-tested-context-tokens", type=int)
    validate_model.add_argument(
        "--memory-pressure",
        choices=("normal", "warning", "critical", "unknown"),
        default="unknown",
    )
    validate_model.add_argument(
        "--thermal-state",
        choices=("nominal", "fair", "serious", "critical", "unknown"),
        default="unknown",
    )
    validate_model.add_argument(
        "--core-cases",
        help="Override the bundled core evaluation suite.",
    )
    validate_model.add_argument(
        "--provider-cases",
        help="Override the bundled provider smoke suite.",
    )
    validate_model.add_argument(
        "--behavior-cases",
        help="Override the bundled behavioral qualification suite.",
    )
    validate_model.add_argument(
        "--output",
        default="validation/ally-local-model.json",
    )

    validate_compare = validate_commands.add_parser(
        "compare",
        help="Compare two or more versioned validation reports without choosing a default.",
    )
    validate_compare.add_argument("reports", nargs="+")
    validate_compare.add_argument("--json", action="store_true", dest="json_output")

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _run_command(argv)
    except DatabaseMigrationError as exc:
        print(f"Database error: {exc}")
        return 2


def _run_command(argv: Sequence[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()

    if args.command == "chat":
        return run_chat(
            endpoint=cast(str, args.endpoint),
            model=cast(str, args.model),
            prompt=cast(str | None, args.prompt),
            conversation_id=cast(str | None, args.conversation),
            instruction_project=cast(str | None, args.instruction_project),
            instruction_task=cast(str | None, args.instruction_task),
            session_instructions=cast(str | None, args.session_instructions),
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

    if args.command == "instructions":
        if args.instructions_command == "show":
            return run_show_instructions(
                scope=cast(InstructionScope, args.scope),
                scope_key=cast(str | None, args.key),
            )
        if args.instructions_command == "set":
            return run_set_instructions(
                content=cast(str, args.content),
                scope=cast(InstructionScope, args.scope),
                scope_key=cast(str | None, args.key),
                enabled=not cast(bool, args.disabled),
            )
        if args.instructions_command == "clear":
            return run_clear_instructions(
                scope=cast(InstructionScope, args.scope),
                scope_key=cast(str | None, args.key),
            )
        if args.instructions_command == "list":
            return run_list_instructions(
                include_disabled=not cast(bool, args.enabled_only),
            )
        if args.instructions_command in {"enable", "disable"}:
            return run_set_instructions_enabled(
                enabled=args.instructions_command == "enable",
                scope=cast(InstructionScope, args.scope),
                scope_key=cast(str | None, args.key),
            )
        if args.instructions_command == "resolve":
            return run_resolve_instructions(
                project_key=cast(str | None, args.project),
                conversation_key=cast(str | None, args.conversation),
                task_key=cast(str | None, args.task),
                session_instructions=cast(str | None, args.session),
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
        if args.memory_command == "propose":
            return run_propose_memories(
                endpoint=cast(str, args.endpoint),
                model=cast(str, args.model),
                text=cast(str, args.text),
                source_type=cast(MemorySourceType, args.source_type),
                source_id=cast(str | None, args.source_id),
                source_uri=cast(str | None, args.source_uri),
                privacy=cast(MemoryPrivacy, args.privacy),
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

    if args.command == "secrets":
        if args.secrets_command == "set":
            return run_set_secret(name=cast(str, args.name))
        if args.secrets_command == "list":
            return run_list_secret_references()
        if args.secrets_command == "check":
            return run_check_secret(name=cast(str, args.name))
        if args.secrets_command == "delete":
            return run_delete_secret(name=cast(str, args.name))

    if args.command == "eval":
        if args.eval_command == "run":
            return run_core_evals(
                case_file=cast(str | None, args.case_file),
                json_output=cast(bool, args.json_output),
            )
        if args.eval_command == "provider":
            return run_provider_evals(
                case_file=cast(str | None, args.case_file),
                endpoint=cast(str, args.endpoint),
                model=cast(str, args.model),
                allow_remote_public=cast(bool, args.allow_remote_public),
                json_output=cast(bool, args.json_output),
            )
        if args.eval_command == "behavior":
            return run_behavior_evals(
                case_file=cast(str | None, args.case_file),
                endpoint=cast(str, args.endpoint),
                model=cast(str, args.model),
                allow_remote_public=cast(bool, args.allow_remote_public),
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
                sink_name=cast(AttentionSinkName, args.sink),
                limit=cast(int, args.limit),
            )
        if args.attention_command == "health":
            return run_attention_sink_health(
                sink_name=cast(AttentionSinkName, args.sink),
                json_output=cast(bool, args.json_output),
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

    if args.command == "service":
        if args.service_command == "cycle":
            return run_proactive_cycle(
                at=cast(str | None, args.at),
                schedule_limit=cast(int, args.schedule_limit),
                delivery_limit=cast(int, args.delivery_limit),
                sink_name=cast(AttentionSinkName, args.sink),
                lease_seconds=cast(int, args.lease_seconds),
                json_output=cast(bool, args.json_output),
            )
        if args.service_command == "leases":
            return run_list_service_leases()
        if args.service_command == "history":
            return run_service_history(
                limit=cast(int, args.limit),
                json_output=cast(bool, args.json_output),
            )
        if args.service_command == "health":
            return run_service_health(
                json_output=cast(bool, args.json_output),
            )
        if args.service_command == "managed" and args.managed_service_command is not None:
            return run_managed_service(
                action=cast(str, args.managed_service_command),
                json_output=cast(bool, getattr(args, "json_output", False)),
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

    if args.command == "sources":
        if args.sources_command == "poll-jsonl":
            return run_poll_jsonl_source(
                source_id=cast(str, args.source_id),
                path=cast(str, args.path),
                limit=cast(int, args.limit),
                at=cast(str | None, args.at),
                json_output=cast(bool, args.json_output),
            )
        if args.sources_command == "poll-filesystem":
            return run_poll_filesystem_source(
                source_id=cast(str, args.source_id),
                root=cast(str, args.root),
                limit=cast(int, args.limit),
                max_entries=cast(int, args.max_entries),
                include_hidden=cast(bool, args.include_hidden),
                importance=cast(EventImportance, args.importance),
                at=cast(str | None, args.at),
                json_output=cast(bool, args.json_output),
            )
        if args.sources_command == "checkpoints":
            return run_list_source_checkpoints(limit=cast(int, args.limit))
        if args.sources_command == "checkpoint":
            return run_show_source_checkpoint(
                source_id=cast(str, args.source_id)
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
        if args.skills_command == "run":
            return run_execute_skill(
                skill_id=cast(str, args.skill_id),
                version=cast(str, args.version),
                input_json=cast(str, args.input),
                timeout_seconds=cast(int, args.timeout_seconds),
            )
        if args.skills_command == "audit":
            return run_skill_execution_audit(limit=cast(int, args.limit))

    if args.command == "validate":
        if args.validate_command == "hardware":
            return run_hardware_report(json_output=cast(bool, args.json_output))
        if args.validate_command == "local-model":
            return run_local_model_validation_command(
                endpoint=cast(str, args.endpoint),
                model=cast(str, args.model),
                runtime_name=cast(str, args.runtime),
                runtime_version=cast(str, args.runtime_version),
                model_source=cast(str | None, args.model_source),
                quantization=cast(str | None, args.quantization),
                precision=cast(str | None, args.precision),
                model_size_bytes=cast(int | None, args.model_size_bytes),
                context_length=cast(int | None, args.context_length),
                runtime_parameters=cast(Sequence[str], args.runtime_parameters),
                model_load_ms=cast(float | None, args.model_load_ms),
                time_to_first_token_ms=cast(float | None, args.time_to_first_token_ms),
                prompt_tokens_per_second=cast(
                    float | None,
                    args.prompt_tokens_per_second,
                ),
                generation_tokens_per_second=cast(
                    float | None,
                    args.generation_tokens_per_second,
                ),
                peak_memory_bytes=cast(int | None, args.peak_memory_bytes),
                maximum_tested_context_tokens=cast(
                    int | None,
                    args.maximum_tested_context_tokens,
                ),
                memory_pressure=cast(str, args.memory_pressure),
                thermal_state=cast(str, args.thermal_state),
                core_case_file=cast(str | None, args.core_cases),
                provider_case_file=cast(str | None, args.provider_cases),
                behavior_case_file=cast(str | None, args.behavior_cases),
                output=cast(str, args.output),
            )
        if args.validate_command == "compare":
            return run_compare_validation_reports(
                report_paths=cast(Sequence[str], args.reports),
                json_output=cast(bool, args.json_output),
            )

    if args.command == "plan" and args.plan_command == "propose":
        return run_propose_plan(
            endpoint=cast(str, args.endpoint),
            model=cast(str, args.model),
            goal=cast(str, args.goal),
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
