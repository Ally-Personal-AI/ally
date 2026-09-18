from ally.cli import build_parser


def test_chat_parser_defaults_to_loopback_endpoint() -> None:
    args = build_parser().parse_args(["chat", "--model", "example"])

    assert args.command == "chat"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.model == "example"
    assert args.allow_remote is False
    assert args.conversation is None


def test_chat_parser_accepts_conversation_resume_id() -> None:
    args = build_parser().parse_args(
        ["chat", "--model", "example", "--conversation", "abc"]
    )

    assert args.conversation == "abc"


def test_conversations_list_parser_defaults_limit() -> None:
    args = build_parser().parse_args(["conversations", "list"])

    assert args.command == "conversations"
    assert args.conversations_command == "list"
    assert args.limit == 20


def test_conversations_show_parser_accepts_identifier() -> None:
    args = build_parser().parse_args(["conversations", "show", "abc"])

    assert args.conversations_command == "show"
    assert args.conversation_id == "abc"
