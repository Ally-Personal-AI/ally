from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ally.memory import MemorySource, NewMemory


def test_memory_requires_timezone_aware_temporal_values() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        NewMemory(
            kind="semantic",
            content="Synthetic fact",
            source=MemorySource(type="user"),
            observed_at=datetime(2026, 1, 1),
        )


def test_memory_rejects_inverted_validity_range() -> None:
    start = datetime(2026, 1, 2, tzinfo=UTC)

    with pytest.raises(ValidationError, match="later than valid_from"):
        NewMemory(
            kind="semantic",
            content="Synthetic fact",
            source=MemorySource(type="user"),
            valid_from=start,
            valid_until=start - timedelta(days=1),
        )
