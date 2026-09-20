"""OpenAI-compatible local HTTP inference provider."""

from __future__ import annotations

from types import TracebackType
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from ally.models.base import ChatRequest, ChatResponse
from ally.models.errors import ProviderConnectionError, ProviderResponseError
from ally.security.network import is_loopback_http_url


class _ResponseMessage(BaseModel):
    content: str


class _ResponseChoice(BaseModel):
    message: _ResponseMessage


class _CompletionResponse(BaseModel):
    model: str | None = None
    choices: list[_ResponseChoice]


class OpenAICompatibleProvider:
    """Adapter for local servers exposing OpenAI-compatible chat completions."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        api_key: str | None = None,
        allow_remote: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized_url = base_url.rstrip("/")
        parsed = urlparse(normalized_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if not allow_remote and not is_loopback_http_url(normalized_url):
            raise ValueError(
                "Remote inference endpoints are disabled by default; "
                "set allow_remote=True explicitly."
            )
        if not model.strip():
            raise ValueError("model cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        headers: dict[str, str] = {}
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"

        self._base_url = normalized_url
        self._model = model
        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers=headers,
            transport=transport,
            # Ambient proxies must not route local prompts off the machine.
            trust_env=False,
        )

    @property
    def name(self) -> str:
        return "openai-compatible"

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAICompatibleProvider:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def chat(self, request: ChatRequest) -> ChatResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
        }

        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"Could not reach inference provider at {self._base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise ProviderResponseError(
                f"Inference provider returned HTTP {status}."
            ) from exc

        try:
            completion = _CompletionResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ProviderResponseError("Inference provider returned invalid JSON.") from exc

        if not completion.choices:
            raise ProviderResponseError("Inference provider returned no choices.")

        return ChatResponse(
            content=completion.choices[0].message.content,
            model=completion.model or self._model,
            provider=self.name,
        )
