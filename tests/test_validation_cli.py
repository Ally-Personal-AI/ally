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
    assert args.model_artifacts == []
    assert args.runtime_artifacts == []
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



def test_validate_candidate_parser_accepts_exact_evidence_set() -> None:
    args = build_parser().parse_args(
        [
            "validate",
            "candidate",
            "validation.json",
            "privacy.json",
            "workflows.json",
            "--json",
        ]
    )

    assert args.validate_command == "candidate"
    assert args.validation_report == "validation.json"
    assert args.privacy_report == "privacy.json"
    assert args.workflow_report == "workflows.json"
    assert args.json_output is True


def test_validate_compare_candidates_parser_accepts_repeated_evidence_sets() -> None:
    args = build_parser().parse_args(
        [
            "validate",
            "compare-candidates",
            "--candidate",
            "a-validation.json",
            "a-privacy.json",
            "a-workflows.json",
            "--candidate",
            "b-validation.json",
            "b-privacy.json",
            "b-workflows.json",
            "--json",
        ]
    )

    assert args.validate_command == "compare-candidates"
    assert args.evidence_sets == [
        ["a-validation.json", "a-privacy.json", "a-workflows.json"],
        ["b-validation.json", "b-privacy.json", "b-workflows.json"],
    ]
    assert args.json_output is True



def test_validate_local_model_parser_accepts_repeated_artifacts() -> None:
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
            "--model-artifact",
            "model-00001.gguf",
            "--model-artifact",
            "model-00002.gguf",
            "--runtime-artifact",
            "llama-server",
        ]
    )

    assert args.model_artifacts == [
        "model-00001.gguf",
        "model-00002.gguf",
    ]
    assert args.runtime_artifacts == ["llama-server"]


def test_validate_readiness_parser_supports_json() -> None:
    args = build_parser().parse_args(
        ["validate", "readiness", "--json"]
    )

    assert args.command == "validate"
    assert args.validate_command == "readiness"
    assert args.json_output is True


def test_validate_workflows_parser_uses_capability_report_source() -> None:
    args = build_parser().parse_args(
        ["validate", "workflows", "validation.json", "--json"]
    )

    assert args.command == "validate"
    assert args.validate_command == "workflows"
    assert args.validation_report == "validation.json"
    assert args.output == "validation/ally-functional-workflows.json"
    assert args.json_output is True


def test_validate_workflows_show_and_verify_parsers_support_json() -> None:
    show = build_parser().parse_args(
        ["validate", "workflows-show", "workflows.json", "--json"]
    )
    verify = build_parser().parse_args(
        [
            "validate",
            "workflows-verify",
            "workflows.json",
            "validation.json",
            "--json",
        ]
    )

    assert show.validate_command == "workflows-show"
    assert show.report == "workflows.json"
    assert show.json_output is True
    assert verify.validate_command == "workflows-verify"
    assert verify.report == "workflows.json"
    assert verify.validation_report == "validation.json"
    assert verify.json_output is True



def test_profiles_create_parser_accepts_complete_evidence_set() -> None:
    args = build_parser().parse_args(
        [
            "profiles",
            "create",
            "validation.json",
            "privacy.json",
            "workflows.json",
            "--output",
            "profile.json",
            "--json",
        ]
    )

    assert args.command == "profiles"
    assert args.profiles_command == "create"
    assert args.validation_report == "validation.json"
    assert args.privacy_report == "privacy.json"
    assert args.workflow_report == "workflows.json"
    assert args.output == "profile.json"
    assert args.json_output is True


def test_profiles_show_and_verify_parsers() -> None:
    show = build_parser().parse_args(
        ["profiles", "show", "profile.json", "--json"]
    )
    verify = build_parser().parse_args(
        [
            "profiles",
            "verify",
            "profile.json",
            "validation.json",
            "privacy.json",
            "workflows.json",
            "--json",
        ]
    )

    assert show.profiles_command == "show"
    assert show.profile == "profile.json"
    assert show.json_output is True
    assert verify.profiles_command == "verify"
    assert verify.profile == "profile.json"
    assert verify.validation_report == "validation.json"
    assert verify.privacy_report == "privacy.json"
    assert verify.workflow_report == "workflows.json"
    assert verify.json_output is True



def test_validation_session_init_parser_requires_directory() -> None:
    args = build_parser().parse_args(
        [
            "validation-session",
            "init",
            "candidate-a",
            "--directory",
            "validation/candidate-a",
            "--json",
        ]
    )

    assert args.command == "validation-session"
    assert args.validation_session_command == "init"
    assert args.candidate_label == "candidate-a"
    assert args.directory == "validation/candidate-a"
    assert args.capability_artifact == "capability.json"
    assert args.privacy_artifact == "privacy.json"
    assert args.workflow_artifact == "workflows.json"
    assert args.profile_artifact == "profile.json"
    assert args.json_output is True


def test_validation_session_show_refresh_verify_parsers() -> None:
    show = build_parser().parse_args(
        ["validation-session", "show", "validation/candidate/session.json"]
    )
    refresh = build_parser().parse_args(
        [
            "validation-session",
            "refresh",
            "validation/candidate/session.json",
            "--json",
        ]
    )
    verify = build_parser().parse_args(
        [
            "validation-session",
            "verify",
            "validation/candidate/session.json",
            "--json",
        ]
    )

    assert show.validation_session_command == "show"
    assert show.session == "validation/candidate/session.json"
    assert refresh.validation_session_command == "refresh"
    assert refresh.json_output is True
    assert verify.validation_session_command == "verify"
    assert verify.json_output is True
