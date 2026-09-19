from ally.security.network import private_grounding_allowed


def test_private_context_is_allowed_for_loopback() -> None:
    assert private_grounding_allowed(
        "http://127.0.0.1:8080/v1",
        allow_remote_private_context=False,
    )


def test_private_context_is_denied_for_remote_without_separate_opt_in() -> None:
    assert not private_grounding_allowed(
        "https://example.com/v1",
        allow_remote_private_context=False,
    )


def test_private_context_can_be_explicitly_allowed_for_remote() -> None:
    assert private_grounding_allowed(
        "https://example.com/v1",
        allow_remote_private_context=True,
    )
