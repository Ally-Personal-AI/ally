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


def test_validate_runtime_privacy_parser_is_fail_closed_by_default() -> None:
    args = build_parser().parse_args(
        ["validate", "runtime-privacy", "validation.json"]
    )

    assert args.validate_command == "runtime-privacy"
    assert args.validation_report == "validation.json"
    assert args.isolation_mode == "unverified"
    assert args.network_observation == "none"
    assert args.inference_with_egress_blocked == "not_run"
    assert args.synthetic_chat == "not_run"
    assert args.synthetic_planning == "not_run"
    assert args.synthetic_memory_proposal == "not_run"
    assert args.synthetic_grounding == "not_run"
    assert args.no_cloud_auth_required == "not_run"
    assert args.no_cloud_fallback_observed == "not_run"
    assert args.no_prompt_telemetry_observed == "not_run"
    assert args.no_unexpected_outbound_connections == "not_run"
    assert args.output == "validation/ally-runtime-privacy.json"


def test_validate_runtime_privacy_show_parser_supports_json() -> None:
    args = build_parser().parse_args(
        ["validate", "runtime-privacy-show", "privacy.json", "--json"]
    )

    assert args.validate_command == "runtime-privacy-show"
    assert args.report == "privacy.json"
    assert args.json_output is True


def test_validate_runtime_privacy_verify_parser_supports_json() -> None:
    args = build_parser().parse_args(
        [
            "validate",
            "runtime-privacy-verify",
            "privacy.json",
            "validation.json",
            "--json",
        ]
    )

    assert args.validate_command == "runtime-privacy-verify"
    assert args.report == "privacy.json"
    assert args.validation_report == "validation.json"
    assert args.json_output is True
