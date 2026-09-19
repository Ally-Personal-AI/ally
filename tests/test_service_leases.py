from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from ally.service import (
    SQLiteServiceLeaseStore,
    ServiceLeaseUnavailableError,
    service_lease,
)
from ally.storage import default_database_path, default_runtime_database_path

OWNER_A = UUID("00000000-0000-0000-0000-000000000001")
OWNER_B = UUID("00000000-0000-0000-0000-000000000002")
BASE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def build_store(path: Path) -> SQLiteServiceLeaseStore:
    return SQLiteServiceLeaseStore(path)


def test_runtime_database_is_separate_from_personal_database() -> None:
    assert default_runtime_database_path() != default_database_path()
    assert default_runtime_database_path().name == "service.sqlite3"
    assert default_runtime_database_path().parent.name == "runtime"


def test_first_owner_acquires_lease(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")

    lease = store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=BASE_TIME,
        ttl_seconds=300,
    )

    assert lease is not None
    assert lease.name == "proactive-cycle"
    assert lease.owner_id == OWNER_A
    assert lease.acquired_at == BASE_TIME
    assert lease.expires_at == BASE_TIME + timedelta(seconds=300)
    assert store.get("proactive-cycle") == lease


def test_second_owner_is_blocked_before_expiry(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    first = store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=BASE_TIME,
        ttl_seconds=300,
    )
    assert first is not None

    blocked = store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_B,
        now=BASE_TIME + timedelta(seconds=299),
        ttl_seconds=300,
    )

    assert blocked is None
    assert store.get("proactive-cycle") == first


def test_expired_lease_can_be_taken_over_atomically(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=BASE_TIME,
        ttl_seconds=30,
    )

    takeover_time = BASE_TIME + timedelta(seconds=30)
    taken = store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_B,
        now=takeover_time,
        ttl_seconds=60,
    )

    assert taken is not None
    assert taken.owner_id == OWNER_B
    assert taken.acquired_at == takeover_time
    assert taken.expires_at == takeover_time + timedelta(seconds=60)


def test_same_owner_can_reacquire_and_refresh_lease(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=BASE_TIME,
        ttl_seconds=30,
    )

    refreshed_at = BASE_TIME + timedelta(seconds=10)
    refreshed = store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=refreshed_at,
        ttl_seconds=90,
    )

    assert refreshed is not None
    assert refreshed.owner_id == OWNER_A
    assert refreshed.acquired_at == refreshed_at
    assert refreshed.expires_at == refreshed_at + timedelta(seconds=90)


def test_current_owner_can_renew_unexpired_lease(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=BASE_TIME,
        ttl_seconds=30,
    )

    renewed_at = BASE_TIME + timedelta(seconds=10)
    renewed = store.renew(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=renewed_at,
        ttl_seconds=60,
    )

    assert renewed is not None
    assert renewed.owner_id == OWNER_A
    assert renewed.acquired_at == BASE_TIME
    assert renewed.expires_at == renewed_at + timedelta(seconds=60)
    assert renewed.updated_at == renewed_at


def test_wrong_or_expired_owner_cannot_renew(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=BASE_TIME,
        ttl_seconds=30,
    )

    assert (
        store.renew(
            name="proactive-cycle",
            owner_id=OWNER_B,
            now=BASE_TIME + timedelta(seconds=10),
            ttl_seconds=60,
        )
        is None
    )
    assert (
        store.renew(
            name="proactive-cycle",
            owner_id=OWNER_A,
            now=BASE_TIME + timedelta(seconds=30),
            ttl_seconds=60,
        )
        is None
    )


def test_release_requires_matching_owner(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=BASE_TIME,
        ttl_seconds=300,
    )

    assert store.release(name="proactive-cycle", owner_id=OWNER_B) is False
    assert store.get("proactive-cycle") is not None
    assert store.release(name="proactive-cycle", owner_id=OWNER_A) is True
    assert store.get("proactive-cycle") is None


def test_service_lease_context_releases_after_normal_exit(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")

    with service_lease(
        store,
        name="proactive-cycle",
        ttl_seconds=300,
        owner_id=OWNER_A,
    ) as lease:
        assert lease.owner_id == OWNER_A
        assert store.get("proactive-cycle") is not None

    assert store.get("proactive-cycle") is None


def test_service_lease_context_releases_after_exception(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")

    with pytest.raises(RuntimeError, match="synthetic"):
        with service_lease(
            store,
            name="proactive-cycle",
            ttl_seconds=300,
            owner_id=OWNER_A,
        ):
            raise RuntimeError("synthetic")

    assert store.get("proactive-cycle") is None


def test_service_lease_context_rejects_existing_owner(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=datetime.now(UTC),
        ttl_seconds=300,
    )

    with pytest.raises(ServiceLeaseUnavailableError, match="already held"):
        with service_lease(
            store,
            name="proactive-cycle",
            ttl_seconds=300,
            owner_id=OWNER_B,
        ):
            raise AssertionError("unreachable")


def test_invalid_name_ttl_and_naive_time_are_rejected(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")

    with pytest.raises(ValueError, match="invalid service lease name"):
        store.acquire(
            name="Invalid Lease",
            owner_id=OWNER_A,
            now=BASE_TIME,
            ttl_seconds=30,
        )

    with pytest.raises(ValueError, match="ttl_seconds"):
        store.acquire(
            name="valid-lease",
            owner_id=OWNER_A,
            now=BASE_TIME,
            ttl_seconds=0,
        )

    with pytest.raises(ValueError, match="timezone offset"):
        store.acquire(
            name="valid-lease",
            owner_id=OWNER_A,
            now=datetime(2026, 1, 1, 12, 0),
            ttl_seconds=30,
        )


def test_list_is_stable_by_name(tmp_path: Path) -> None:
    store = build_store(tmp_path / "runtime.sqlite3")
    for name in ("zeta", "alpha"):
        store.acquire(
            name=name,
            owner_id=OWNER_A,
            now=BASE_TIME,
            ttl_seconds=300,
        )

    assert [record.name for record in store.list()] == ["alpha", "zeta"]


def test_proactive_command_stops_before_side_effects_when_lease_is_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ally.commands.service as service_commands

    store = build_store(tmp_path / "runtime.sqlite3")
    acquired = store.acquire(
        name="proactive-cycle",
        owner_id=OWNER_A,
        now=datetime.now(UTC),
        ttl_seconds=300,
    )
    assert acquired is not None

    monkeypatch.setattr(
        service_commands,
        "build_service_lease_store",
        lambda: store,
    )

    def fail_if_called() -> None:
        raise AssertionError("event storage must not be constructed")

    monkeypatch.setattr(
        service_commands,
        "build_event_store",
        fail_if_called,
    )

    result = service_commands.run_proactive_cycle(
        at=None,
        schedule_limit=100,
        delivery_limit=50,
        sink_name="console",
        lease_seconds=300,
        json_output=False,
    )

    assert result == 2
