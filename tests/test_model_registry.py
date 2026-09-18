import pytest

from ally.models import ChatRequest, ChatResponse, ModelRegistry


class FakeProvider:
    @property
    def name(self) -> str:
        return "fake"

    def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(content="ok", model="fake-model", provider=self.name)


def test_registry_registers_and_resolves_provider() -> None:
    registry = ModelRegistry()
    provider = FakeProvider()

    registry.register(provider)

    assert registry.get("fake") is provider
    assert registry.names() == ("fake",)


def test_registry_rejects_duplicate_provider_names() -> None:
    registry = ModelRegistry()
    registry.register(FakeProvider())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeProvider())
