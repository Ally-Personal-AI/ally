from ally.context.lexical import bm25_scores, lexical_terms, lexical_tokens


def test_lexical_terms_preserve_frequency_while_tokens_remain_unique() -> None:
    assert lexical_terms("Orchard orchard and irrigation") == (
        "orchard",
        "orchard",
        "irrigation",
    )
    assert lexical_tokens("Orchard orchard and irrigation") == frozenset(
        {"orchard", "irrigation"}
    )


def test_bm25_rare_query_term_outweighs_common_term() -> None:
    documents = (
        "common alpha",
        "common beta",
        "rare gamma",
    )

    scores = bm25_scores("common rare", documents)

    assert scores[2] > scores[0]
    assert scores[2] > scores[1]


def test_bm25_term_frequency_improves_relevance_without_external_state() -> None:
    documents = (
        "orchard orchard orchard irrigation",
        "orchard maintenance schedule equipment tractor",
    )

    scores = bm25_scores("orchard", documents)

    assert scores[0] > scores[1]


def test_bm25_empty_or_stopword_query_returns_zero_scores() -> None:
    assert bm25_scores("", ("alpha", "beta")) == (0.0, 0.0)
    assert bm25_scores("the and of", ("alpha", "beta")) == (0.0, 0.0)
