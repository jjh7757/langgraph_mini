import pytest

from langgraph_mini.orchestration.domain import PendingRequest, PendingRequestNotFoundError, PendingStatus
from langgraph_mini.orchestration.pending_repository_json import JsonPendingRepository


def _request(request_id: str, thread_id: str) -> PendingRequest:
    return PendingRequest(
        request_id=request_id,
        thread_id=thread_id,
        requester_id="u1",
        action="billing.pay_bills",
        params={"account_id": "a1", "bill_ids": ["b1", "b2"]},
    )


def test_save_then_find_by_id(tmp_path):
    repo = JsonPendingRepository(tmp_path / "pending_requests.json")
    request = _request("r1", "t1")

    repo.save(request)

    assert repo.find_by_id("r1") == request


def test_find_by_id_raises_when_not_found(tmp_path):
    repo = JsonPendingRepository(tmp_path / "pending_requests.json")

    with pytest.raises(PendingRequestNotFoundError):
        repo.find_by_id("no-such-request")


def test_find_by_thread_id_returns_only_that_threads_requests(tmp_path):
    repo = JsonPendingRepository(tmp_path / "pending_requests.json")
    request1 = _request("r1", "t1")
    request2 = _request("r2", "t2")
    repo.save(request1)
    repo.save(request2)

    assert repo.find_by_thread_id("t1") == [request1]


def test_data_survives_reopening_the_repository_for_recovery(tmp_path):
    """재시작·장애 복구가 실제로 의존하는 동작 — 프로세스가 다시 떠도 PENDING 상태가
    파일에 남아있어야 get_pending(thread_id)로 다시 찾을 수 있음."""
    path = tmp_path / "pending_requests.json"
    repo = JsonPendingRepository(path)
    repo.save(_request("r1", "t1"))

    reopened = JsonPendingRepository(path)

    request = reopened.find_by_id("r1")
    assert request.status is PendingStatus.PENDING
    assert request.params == {"account_id": "a1", "bill_ids": ["b1", "b2"]}
