from ally.cli import build_parser


def test_chat_parser_defaults_to_loopback_endpoint() -> None:
    args = build_parser().parse_args(["chat", "--model", "example"])

    assert args.command == "chat"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.model == "example"
    assert args.allow_remote is False
    assert args.allow_private_context_remote is False
    assert args.conversation is None


def test_chat_parser_accepts_conversation_resume_id() -> None:
    args = build_parser().parse_args(
        ["chat", "--model", "example", "--conversation", "abc"]
    )

    assert args.conversation == "abc"


def test_chat_parser_requires_separate_private_context_remote_flag() -> None:
    args = build_parser().parse_args(
        [
            "chat",
            "--model",
            "example",
            "--allow-remote",
            "--allow-private-context-remote",
        ]
    )

    assert args.allow_remote is True
    assert args.allow_private_context_remote is True


def test_conversations_list_parser_defaults_limit() -> None:
    args = build_parser().parse_args(["conversations", "list"])

    assert args.command == "conversations"
    assert args.conversations_command == "list"
    assert args.limit == 20


def test_conversations_show_parser_accepts_identifier() -> None:
    args = build_parser().parse_args(["conversations", "show", "abc"])

    assert args.conversations_command == "show"
    assert args.conversation_id == "abc"


def test_memory_remember_parser_has_safe_defaults() -> None:
    args = build_parser().parse_args(["memory", "remember", "Synthetic fact"])

    assert args.command == "memory"
    assert args.memory_command == "remember"
    assert args.kind == "semantic"
    assert args.confidence == 1.0
    assert args.importance == 0.5
    assert args.privacy == "private"


def test_memory_list_parser_defaults_to_active_memories() -> None:
    args = build_parser().parse_args(["memory", "list"])

    assert args.memory_command == "list"
    assert args.include_inactive is False
    assert args.limit == 50


def test_memory_supersede_parser_accepts_replacement_content() -> None:
    args = build_parser().parse_args(
        ["memory", "supersede", "synthetic-id", "Replacement fact"]
    )

    assert args.memory_id == "synthetic-id"
    assert args.content == "Replacement fact"


def test_knowledge_ingest_parser_accepts_path() -> None:
    args = build_parser().parse_args(["knowledge", "ingest", "notes.txt"])

    assert args.command == "knowledge"
    assert args.knowledge_command == "ingest"
    assert args.path == "notes.txt"


def test_knowledge_search_parser_has_bounded_default() -> None:
    args = build_parser().parse_args(["knowledge", "search", "greenhouse"])

    assert args.knowledge_command == "search"
    assert args.query == "greenhouse"
    assert args.limit == 8


def test_eval_run_parser_accepts_case_file() -> None:
    args = build_parser().parse_args(["eval", "run", "cases.jsonl"])

    assert args.command == "eval"
    assert args.eval_command == "run"
    assert args.case_file == "cases.jsonl"
    assert args.json_output is False


def test_eval_provider_parser_defaults_to_loopback() -> None:
    args = build_parser().parse_args(
        ["eval", "provider", "provider.jsonl", "--model", "example"]
    )

    assert args.eval_command == "provider"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.model == "example"
    assert args.allow_remote is False


def test_tools_list_parser() -> None:
    args = build_parser().parse_args(["tools", "list"])

    assert args.command == "tools"
    assert args.tools_command == "list"


def test_tools_run_parser_uses_empty_arguments_by_default() -> None:
    args = build_parser().parse_args(["tools", "run", "system.info"])

    assert args.tools_command == "run"
    assert args.name == "system.info"
    assert args.arguments == "{}"
    assert args.approved is False


def test_tools_audit_parser_has_bounded_default() -> None:
    args = build_parser().parse_args(["tools", "audit"])

    assert args.tools_command == "audit"
    assert args.limit == 20


def test_tasks_create_parser_accepts_plan_file() -> None:
    args = build_parser().parse_args(["tasks", "create", "task.json"])

    assert args.command == "tasks"
    assert args.tasks_command == "create"
    assert args.plan_path == "task.json"


def test_tasks_run_parser_collects_explicit_step_approvals() -> None:
    args = build_parser().parse_args(
        [
            "tasks",
            "run",
            "task-id",
            "--approve-step",
            "step-a",
            "--approve-step",
            "step-b",
        ]
    )

    assert args.tasks_command == "run"
    assert args.approved_steps == ["step-a", "step-b"]


def test_tasks_list_parser_has_bounded_default() -> None:
    args = build_parser().parse_args(["tasks", "list"])

    assert args.tasks_command == "list"
    assert args.limit == 20


def test_skills_inspect_parser_accepts_package_path() -> None:
    args = build_parser().parse_args(["skills", "inspect", "./skill"])

    assert args.command == "skills"
    assert args.skills_command == "inspect"
    assert args.path == "./skill"


def test_skills_validate_parser_collects_available_tools() -> None:
    args = build_parser().parse_args(
        [
            "skills",
            "validate",
            "./skill",
            "--available-tool",
            "system.info",
            "--available-tool",
            "files.read",
        ]
    )

    assert args.skills_command == "validate"
    assert args.available_tools == ["system.info", "files.read"]


def test_plan_propose_parser_defaults_to_loopback() -> None:
    args = build_parser().parse_args(
        [
            "plan",
            "propose",
            "--model",
            "example",
            "--goal",
            "Inspect runtime",
        ]
    )

    assert args.command == "plan"
    assert args.plan_command == "propose"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.model == "example"
    assert args.goal == "Inspect runtime"
    assert args.allow_remote is False


def test_memory_propose_parser_has_local_safe_defaults() -> None:
    args = build_parser().parse_args(
        [
            "memory",
            "propose",
            "I prefer tea.",
            "--model",
            "example",
        ]
    )

    assert args.memory_command == "propose"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.model == "example"
    assert args.text == "I prefer tea."
    assert args.allow_remote is False
    assert args.source_type == "user"
    assert args.privacy == "private"
    assert args.output is None


def test_memory_accept_parser_collects_selected_indices() -> None:
    args = build_parser().parse_args(
        [
            "memory",
            "accept",
            "proposal.json",
            "--index",
            "0",
            "--index",
            "2",
        ]
    )

    assert args.memory_command == "accept"
    assert args.proposal_path == "proposal.json"
    assert args.indices == [0, 2]


def test_events_emit_parser_has_conservative_defaults() -> None:
    args = build_parser().parse_args(["events", "emit", "calendar.changed"])

    assert args.command == "events"
    assert args.events_command == "emit"
    assert args.event_type == "calendar.changed"
    assert args.source == "cli"
    assert args.importance == "routine"
    assert args.payload == "{}"


def test_events_list_parser_can_filter_pending_notifications() -> None:
    args = build_parser().parse_args(
        [
            "events",
            "list",
            "--attention",
            "notify",
            "--pending",
        ]
    )

    assert args.events_command == "list"
    assert args.attention == "notify"
    assert args.handled is False
    assert args.limit == 50


def test_events_show_and_handle_accept_identifiers() -> None:
    show = build_parser().parse_args(["events", "show", "event-id"])
    handle = build_parser().parse_args(["events", "handle", "event-id"])

    assert show.events_command == "show"
    assert show.event_id == "event-id"
    assert handle.events_command == "handle"
    assert handle.event_id == "event-id"


def test_data_backup_parser_accepts_archive_path() -> None:
    args = build_parser().parse_args(["data", "backup", "backup.ally-backup"])

    assert args.command == "data"
    assert args.data_command == "backup"
    assert args.output == "backup.ally-backup"


def test_data_validate_parser_accepts_archive_path() -> None:
    args = build_parser().parse_args(["data", "validate", "backup.ally-backup"])

    assert args.data_command == "validate"
    assert args.archive == "backup.ally-backup"


def test_data_restore_parser_defaults_destination() -> None:
    args = build_parser().parse_args(["data", "restore", "backup.ally-backup"])

    assert args.data_command == "restore"
    assert args.archive == "backup.ally-backup"
    assert args.destination is None


def test_config_path_parser() -> None:
    args = build_parser().parse_args(["config", "path"])

    assert args.command == "config"
    assert args.config_command == "path"


def test_config_init_parser() -> None:
    args = build_parser().parse_args(["config", "init"])

    assert args.config_command == "init"


def test_config_show_parser() -> None:
    args = build_parser().parse_args(["config", "show"])

    assert args.config_command == "show"


def test_config_validate_parser() -> None:
    args = build_parser().parse_args(["config", "validate"])

    assert args.config_command == "validate"


def test_skills_install_parser_accepts_local_path() -> None:
    args = build_parser().parse_args(["skills", "install", "./skill"])

    assert args.skills_command == "install"
    assert args.path == "./skill"


def test_skills_installed_parser() -> None:
    args = build_parser().parse_args(["skills", "installed"])

    assert args.skills_command == "installed"


def test_skills_enable_disable_uninstall_parsers() -> None:
    enable = build_parser().parse_args(
        ["skills", "enable", "sample.skill", "1.0.0"]
    )
    disable = build_parser().parse_args(
        ["skills", "disable", "sample.skill", "1.0.0"]
    )
    uninstall = build_parser().parse_args(
        ["skills", "uninstall", "sample.skill", "1.0.0"]
    )

    assert enable.skills_command == "enable"
    assert disable.skills_command == "disable"
    assert uninstall.skills_command == "uninstall"
    assert enable.skill_id == "sample.skill"
    assert enable.version == "1.0.0"


def test_schedules_create_parser_has_safe_defaults() -> None:
    args = build_parser().parse_args(
        [
            "schedules",
            "create",
            "--name",
            "Synthetic",
            "--event-type",
            "synthetic.event",
            "--at",
            "2026-01-01T12:00:00+00:00",
        ]
    )

    assert args.command == "schedules"
    assert args.schedules_command == "create"
    assert args.name == "Synthetic"
    assert args.event_type == "synthetic.event"
    assert args.at == "2026-01-01T12:00:00+00:00"
    assert args.every_seconds is None
    assert args.importance == "routine"
    assert args.payload == "{}"
    assert args.disabled is False


def test_schedules_create_parser_accepts_interval_and_disabled() -> None:
    args = build_parser().parse_args(
        [
            "schedules",
            "create",
            "--name",
            "Recurring",
            "--event-type",
            "synthetic.interval",
            "--at",
            "2026-01-01T12:00:00+00:00",
            "--every-seconds",
            "300",
            "--disabled",
        ]
    )

    assert args.every_seconds == 300
    assert args.disabled is True


def test_schedules_tick_parser_is_bounded() -> None:
    args = build_parser().parse_args(
        [
            "schedules",
            "tick",
            "--at",
            "2026-01-01T12:00:00+00:00",
        ]
    )

    assert args.schedules_command == "tick"
    assert args.at == "2026-01-01T12:00:00+00:00"
    assert args.limit == 100


def test_schedules_management_parsers_accept_identifier() -> None:
    show = build_parser().parse_args(["schedules", "show", "schedule-id"])
    enable = build_parser().parse_args(["schedules", "enable", "schedule-id"])
    disable = build_parser().parse_args(["schedules", "disable", "schedule-id"])

    assert show.schedules_command == "show"
    assert enable.schedules_command == "enable"
    assert disable.schedules_command == "disable"
    assert show.schedule_id == "schedule-id"


def test_attention_pending_parser_has_bounded_default() -> None:
    args = build_parser().parse_args(["attention", "pending"])

    assert args.command == "attention"
    assert args.attention_command == "pending"
    assert args.limit == 50


def test_attention_deliver_parser_defaults_to_console() -> None:
    args = build_parser().parse_args(["attention", "deliver"])

    assert args.attention_command == "deliver"
    assert args.sink == "console"
    assert args.limit == 50


def test_attention_history_parser_accepts_status_filter() -> None:
    args = build_parser().parse_args(
        ["attention", "history", "--status", "failed"]
    )

    assert args.attention_command == "history"
    assert args.status == "failed"
    assert args.limit == 50
