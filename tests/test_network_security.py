from ally.security.network import is_loopback_http_url


def test_loopback_http_url_detection() -> None:
    assert is_loopback_http_url("http://127.0.0.1:8080/v1")
    assert is_loopback_http_url("http://localhost:11434/v1")
    assert is_loopback_http_url("http://[::1]:8080/v1")


def test_remote_or_invalid_urls_are_not_loopback() -> None:
    assert not is_loopback_http_url("https://example.com/v1")
    assert not is_loopback_http_url("not-a-url")
