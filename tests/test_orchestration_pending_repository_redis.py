import pytest

from langgraph_mini.orchestration.domain import ActionResult, PendingRequest, PendingStatus
from langgraph_mini.orchestration.pending_repository_redis import RedisPendingRepository


def _request(**overrides) -> PendingRequest:
    defaults = dict(
        request_id="r1",
        thread_id="t1",
        requester_id="u1",
        action="account.transfer",
        params={"from_id": "a1", "to_id": "a2", "amount": 1000},
        status=PendingStatus.PENDING,
    )
    defaults.update(overrides)
    return PendingRequest(**defaults)


def test_save_then_find_by_id(redis_client):
    repo = RedisPendingRepository(redis_client)
    request = _request()

    repo.save(request)

    assert repo.find_by_id("r1") == request


def test_find_by_id_raises_when_not_found(redis_client):
    from langgraph_mini.orchestration.domain import PendingRequestNotFoundError

    repo = RedisPendingRepository(redis_client)

    with pytest.raises(PendingRequestNotFoundError):
        repo.find_by_id("no-such-request")


def test_find_by_thread_id_filters(redis_client):
    repo = RedisPendingRepository(redis_client)
    r1 = _request(request_id="r1", thread_id="t1")
    r2 = _request(request_id="r2", thread_id="t2")
    repo.save(r1)
    repo.save(r2)

    assert repo.find_by_thread_id("t1") == [r1]


def test_save_deletes_key_once_no_longer_pending(redis_client):
    """approve/reject 이후(PENDING이 아니게 됨) 재-save하면 Redis에서 지워져야 한다 —
    완료 이력은 Postgres(completed_repo)가 영구 보관하므로 Redis엔 안 남긴다."""
    repo = RedisPendingRepository(redis_client)
    request = _request()
    repo.save(request)

    request.status = PendingStatus.EXECUTED
    request.result = ActionResult(success=True, value=None)
    repo.save(request)

    assert redis_client.get("pending:r1") is None
    assert repo.find_by_thread_id("t1") == []
