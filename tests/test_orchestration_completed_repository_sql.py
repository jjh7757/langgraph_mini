from datetime import datetime

from langgraph_mini.orchestration.completed_repository_sql import SqlCompletedRequestRepository
from langgraph_mini.orchestration.domain import ActionResult, PendingRequest, PendingStatus


def _request(**overrides) -> PendingRequest:
    defaults = dict(
        request_id="r1",
        thread_id="t1",
        requester_id="u1",
        action="account.transfer",
        params={"from_id": "a1", "to_id": "a2", "amount": 1000},
        status=PendingStatus.EXECUTED,
        result=ActionResult(success=True, value=[{"amount": 1000}]),
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        resolved_at=datetime(2026, 1, 1, 12, 0, 5),
    )
    defaults.update(overrides)
    return PendingRequest(**defaults)


def test_save_then_find_by_request_id_round_trips_nested_fields(pg_conn):
    repo = SqlCompletedRequestRepository()
    request = _request()

    repo.save(request)

    assert repo.find_by_request_id("r1") == request


def test_find_by_request_id_returns_none_when_not_found(pg_conn):
    repo = SqlCompletedRequestRepository()

    assert repo.find_by_request_id("no-such-request") is None


def test_find_by_thread_id_filters(pg_conn):
    repo = SqlCompletedRequestRepository()
    r1 = _request(request_id="r1", thread_id="t1")
    r2 = _request(request_id="r2", thread_id="t2")
    repo.save(r1)
    repo.save(r2)

    assert repo.find_by_thread_id("t1") == [r1]


def test_save_upserts_on_conflict(pg_conn):
    repo = SqlCompletedRequestRepository()
    repo.save(_request(status=PendingStatus.PENDING, result=None, resolved_at=None))

    repo.save(_request(status=PendingStatus.REJECTED, result=None))

    assert repo.find_by_request_id("r1").status is PendingStatus.REJECTED
