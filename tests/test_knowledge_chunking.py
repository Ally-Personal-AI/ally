from ally.knowledge.chunking import chunk_text


def test_chunk_text_preserves_exact_source_offsets() -> None:
    text = ("alpha beta gamma " * 150).strip()

    chunks = chunk_text(text, max_chars=240, overlap_chars=40)

    assert len(chunks) > 1
    for ordinal, chunk in enumerate(chunks):
        assert chunk.ordinal == ordinal
        assert text[chunk.start_char : chunk.end_char] == chunk.content
        assert len(chunk.content) <= 240


def test_chunk_text_returns_empty_for_whitespace() -> None:
    assert chunk_text("   \n\t ") == ()


def test_chunk_text_validates_configuration() -> None:
    import pytest

    with pytest.raises(ValueError, match="at least 200"):
        chunk_text("content", max_chars=100)

    with pytest.raises(ValueError, match="smaller than max_chars"):
        chunk_text("content", max_chars=200, overlap_chars=200)
