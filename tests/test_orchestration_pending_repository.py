import pytest

from langgraph_mini.orchestration.domain import PendingRequest, PendingRequestNotFoundError
from langgraph_mini.orchestration.pending_repository import MemoryPendingRepository


def _request(request_id: str, thread_id: str) -> PendingRequest:
    return PendingRequest(
        request_id=request_id,
        thread_id=thread_id,
        requester_id="u1",
        action="card.block_as_lost",
        params={"card_id": "c1"},
    )


def test_save_then_find_by_id():
    repo = MemoryPendingRepository()
    request = _request("r1", "t1")

    repo.save(request)

    assert repo.find_by_id("r1") == request


def test_find_by_id_raises_when_not_found():
    repo = MemoryPendingRepository()

    with pytest.raises(PendingRequestNotFoundError):
        repo.find_by_id("no-such-request")


def test_find_by_thread_id_returns_only_that_threads_requests():
    repo = MemoryPendingRepository()
    request1 = _request("r1", "t1")
    request2 = _request("r2", "t1")
    request3 = _request("r3", "t2")
    repo.save(request1)
    repo.save(request2)
    repo.save(request3)

    assert repo.find_by_thread_id("t1") == [request1, request2]


def test_find_by_thread_id_returns_empty_list_when_none():
    repo = MemoryPendingRepository()

    assert repo.find_by_thread_id("no-such-thread") == []
