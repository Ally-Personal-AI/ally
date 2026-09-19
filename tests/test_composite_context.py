from ally.context import CompositeContextProvider, ContextBlock


class ProviderStub:
    def __init__(self, prefix: str, count: int) -> None:
        self._prefix = prefix
        self._count = count

    def retrieve(self, query: str) -> tuple[ContextBlock, ...]:
        return tuple(
            ContextBlock(
                source=f"{self._prefix}:{index}",
                content=f"{query}:{index}",
            )
            for index in range(self._count)
        )


def test_composite_context_respects_global_limit() -> None:
    provider = CompositeContextProvider(
        (ProviderStub("a", 5), ProviderStub("b", 5)),
        limit=7,
    )

    blocks = provider.retrieve("query")

    assert len(blocks) == 7
    assert [block.source for block in blocks] == [
        "a:0",
        "a:1",
        "a:2",
        "a:3",
        "a:4",
        "b:0",
        "b:1",
    ]
