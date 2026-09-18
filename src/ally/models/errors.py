"""Model-provider errors normalized by Ally."""

from __future__ import annotations


class ModelProviderError(RuntimeError):
    """Base error for inference-provider failures."""


class ProviderConnectionError(ModelProviderError):
    """Raised when Ally cannot reach an inference provider."""


class ProviderResponseError(ModelProviderError):
    """Raised when an inference provider returns an invalid response."""
