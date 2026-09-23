from ally.cli import build_parser


def test_validate_hardware_parser_defaults_to_text() -> None:
    args = build_parser().parse_args(["validate", "hardware"])

    assert args.command == "validate"
    assert args.validate_command == "hardware"
    assert args.json_output is False


def test_validate_local_model_parser_has_reproducible_defaults() -> None:
    args = build_parser().parse_args(
        [
            "validate",
            "local-model",
            "--model",
            "example",
            "--runtime",
            "llama.cpp",
            "--runtime-version",
            "b1234",
        ]
    )

    assert args.validate_command == "local-model"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.core_cases is None
    assert args.provider_cases is None
    assert args.behavior_cases is None
    assert args.output == "validation/ally-local-model.json"
    assert args.runtime == "llama.cpp"
    assert args.runtime_version == "b1234"
    assert args.runtime_parameters == []
    assert args.memory_pressure == "unknown"


def test_validate_compare_parser_accepts_multiple_reports() -> None:
    args = build_parser().parse_args(
        ["validate", "compare", "first.json", "second.json", "--json"]
    )

    assert args.validate_command == "compare"
    assert args.reports == ["first.json", "second.json"]
    assert args.json_output is True
