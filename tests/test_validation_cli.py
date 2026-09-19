from ally.cli import build_parser


def test_validate_hardware_parser_defaults_to_text() -> None:
    args = build_parser().parse_args(["validate", "hardware"])

    assert args.command == "validate"
    assert args.validate_command == "hardware"
    assert args.json_output is False


def test_validate_local_model_parser_has_reproducible_defaults() -> None:
    args = build_parser().parse_args(
        ["validate", "local-model", "--model", "example"]
    )

    assert args.validate_command == "local-model"
    assert args.endpoint == "http://127.0.0.1:8080/v1"
    assert args.core_cases == "evals/cases/core.jsonl"
    assert args.provider_cases == "evals/cases/provider-smoke.jsonl"
    assert args.output == "validation/ally-local-model.json"
