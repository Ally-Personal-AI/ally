from ally.cli import build_parser


def test_chat_parser_defaults_to_loopback_endpoint() -> None:
    args = build_parser().parse_args(["chat", "--model", "example"])

    assert args.command == "chat"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.model == "example"
    assert args.allow_remote is False
