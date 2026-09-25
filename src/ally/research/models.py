"""Provider-neutral models for privacy-gated public web research."""

from __future__ import annotations

import re
from typing import Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ally.egress import EgressDecision, EgressStatus

MAX_RESEARCH_QUERY_CHARS = 600
MAX_RESEARCH_QUERY_WORDS = 75
MAX_RESEARCH_RESULTS = 20


class WebSearchRequest(BaseModel):
    """One exact query proposed for explicit external disclosure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS)
    count: int = Field(default=5, ge=1, le=MAX_RESEARCH_RESULTS)

    @model_validator(mode="after")
    def validate_query(self) -> Self:
        if self.query != self.query.strip():
            raise ValueError("research query must not have leading or trailing whitespace")
        if any(ord(character) < 32 or ord(character) == 127 for character in self.query):
            raise ValueError("research query must be printable single-line text")
        if len(self.query.split()) > MAX_RESEARCH_QUERY_WORDS:
            raise ValueError("research query exceeds the word limit")
        return self


class WebSearchResult(BaseModel):
    """One bounded normalized public search result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=4_000)
    description: str = Field(default="", max_length=2_000)

    @model_validator(mode="after")
    def validate_url(self) -> Self:
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("research result URL must be HTTP(S)")
        return self


class WebSearchPayload(BaseModel):
    """Normalized adapter output consumed only inside Ally."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    results: tuple[WebSearchResult, ...] = Field(max_length=MAX_RESEARCH_RESULTS)
    more_results_available: bool = False


class WebResearchExecution(BaseModel):
    """Application-facing result of one policy-enforced search attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    service: str = Field(min_length=1, max_length=128)
    operation: str = Field(min_length=1, max_length=128)
    decision: EgressDecision
    status: EgressStatus
    results: tuple[WebSearchResult, ...] = Field(
        default=(),
        max_length=MAX_RESEARCH_RESULTS,
    )
    more_results_available: bool = False
    error_class: str | None = Field(default=None, max_length=128)


_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


class WebResearchSynthesis(BaseModel):
    """One locally generated answer whose source markers are machine-checkable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str = Field(min_length=1, max_length=20_000)
    cited_result_indices: tuple[int, ...] = Field(
        default=(),
        max_length=MAX_RESEARCH_RESULTS,
    )
    insufficient_evidence: bool = False

    @model_validator(mode="after")
    def validate_citations(self) -> Self:
        if tuple(sorted(set(self.cited_result_indices))) != self.cited_result_indices:
            raise ValueError("research citations must be unique and sorted")
        if any(index < 1 or index > MAX_RESEARCH_RESULTS for index in self.cited_result_indices):
            raise ValueError("research citation index is outside the supported range")

        markers = tuple(
            sorted({int(value) for value in _CITATION_PATTERN.findall(self.answer)})
        )
        if markers != self.cited_result_indices:
            raise ValueError("research answer citation markers do not match citation metadata")
        if not self.insufficient_evidence and not self.cited_result_indices:
            raise ValueError("sufficient research answers require at least one citation")
        return self


class WebResearchAnswerExecution(BaseModel):
    """Approved search execution plus optional local-only answer synthesis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    search: WebResearchExecution
    synthesis: WebResearchSynthesis | None = None
