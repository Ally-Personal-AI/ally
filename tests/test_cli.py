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
