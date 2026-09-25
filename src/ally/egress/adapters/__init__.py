"""Reviewed concrete external-service transport adapters.

Network-capable dependencies belong in this package. The surrounding egress
models, policy, executor, and audit layers remain transport-independent.
"""

from ally.egress.adapters.brave_search import (
    BRAVE_SEARCH_ENDPOINT,
    BRAVE_SEARCH_SECRET_REF,
    BraveSearchAdapter,
    BraveSearchAdapterError,
    BraveSearchCredentialError,
    BraveSearchResponseError,
)

__all__ = [
    "BRAVE_SEARCH_ENDPOINT",
    "BRAVE_SEARCH_SECRET_REF",
    "BraveSearchAdapter",
    "BraveSearchAdapterError",
    "BraveSearchCredentialError",
    "BraveSearchResponseError",
]
