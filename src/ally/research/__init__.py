"""Privacy-gated public web research."""

from ally.research.models import (
    MAX_RESEARCH_QUERY_CHARS,
    MAX_RESEARCH_QUERY_WORDS,
    MAX_RESEARCH_RESULTS,
    WebResearchAnswerExecution,
    WebResearchExecution,
    WebResearchSynthesis,
    WebSearchPayload,
    WebSearchRequest,
    WebSearchResult,
)
from ally.research.service import (
    WEB_SEARCH_OPERATION,
    ResearchService,
    ResearchServiceError,
)
from ally.research.synthesis import ResearchSynthesisError, WebResearchSynthesizer

__all__ = [
    "MAX_RESEARCH_QUERY_CHARS",
    "MAX_RESEARCH_QUERY_WORDS",
    "MAX_RESEARCH_RESULTS",
    "WEB_SEARCH_OPERATION",
    "ResearchService",
    "ResearchServiceError",
    "WebResearchAnswerExecution",
    "WebResearchExecution",
    "WebResearchSynthesis",
    "WebResearchSynthesizer",
    "ResearchSynthesisError",
    "WebSearchPayload",
    "WebSearchRequest",
    "WebSearchResult",
]