from ally.commands.chat import _private_context_allowed


def test_private_context_is_allowed_for_loopback() -> None:
    assert _private_context_allowed(
        "http://127.0.0.1:8080/v1",
        allow_private_context_remote=False,
    )


def test_private_context_is_denied_for_remote_without_separate_opt_in() -> None:
    assert not _private_context_allowed(
        "https://example.com/v1",
        allow_private_context_remote=False,
    )


def test_private_context_can_be_explicitly_allowed_for_remote() -> None:
    assert _private_context_allowed(
        "https://example.com/v1",
        allow_private_context_remote=True,
    )
