"""Privacy-gated public web research."""

from ally.research.models import (
    MAX_RESEARCH_QUERY_CHARS,
    MAX_RESEARCH_QUERY_WORDS,
    MAX_RESEARCH_RESULTS,
    WebResearchExecution,
    WebSearchPayload,
    WebSearchRequest,
    WebSearchResult,
)
from ally.research.service import (
    WEB_SEARCH_OPERATION,
    ResearchService,
    ResearchServiceError,
)

__all__ = [
    "MAX_RESEARCH_QUERY_CHARS",
    "MAX_RESEARCH_QUERY_WORDS",
    "MAX_RESEARCH_RESULTS",
    "WEB_SEARCH_OPERATION",
    "ResearchService",
    "ResearchServiceError",
    "WebResearchExecution",
    "WebSearchPayload",
    "WebSearchRequest",
    "WebSearchResult",
]
