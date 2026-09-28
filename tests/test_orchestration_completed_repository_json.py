from langgraph_mini.orchestration.completed_repository_json import JsonCompletedRequestRepository
from langgraph_mini.orchestration.domain import ActionResult, PendingRequest, PendingStatus


def _request(request_id: str, thread_id: str) -> PendingRequest:
    return PendingRequest(
        request_id=request_id,
        thread_id=thread_id,
        requester_id="u1",
        action="card.block_as_lost",
        params={"card_id": "c1"},
        status=PendingStatus.EXECUTED,
        result=ActionResult(success=True, value={"card_id": "c1", "status": "분실정지"}),
    )


def test_save_then_find_by_request_id(tmp_path):
    repo = JsonCompletedRequestRepository(tmp_path / "completed_requests.json")
    request = _request("r1", "t1")

    repo.save(request)

    assert repo.find_by_request_id("r1") == request


def test_find_by_request_id_returns_none_when_not_found(tmp_path):
    repo = JsonCompletedRequestRepository(tmp_path / "completed_requests.json")

    assert repo.find_by_request_id("no-such-request") is None


def test_find_by_thread_id_returns_only_that_threads_requests(tmp_path):
    repo = JsonCompletedRequestRepository(tmp_path / "completed_requests.json")
    request1 = _request("r1", "t1")
    request2 = _request("r2", "t2")
    repo.save(request1)
    repo.save(request2)

    assert repo.find_by_thread_id("t1") == [request1]


def test_data_survives_reopening_the_repository(tmp_path):
    """멱등성이 실제로 의존하는 동작 — 프로세스가 다시 떠도 완료 이력이 남아있어야
    같은 request_id 재요청 시 재실행을 막을 수 있음."""
    path = tmp_path / "completed_requests.json"
    repo = JsonCompletedRequestRepository(path)
    repo.save(_request("r1", "t1"))

    reopened = JsonCompletedRequestRepository(path)

    request = reopened.find_by_request_id("r1")
    assert request.status is PendingStatus.EXECUTED
    assert request.result.success is True
    assert request.result.value == {"card_id": "c1", "status": "분실정지"}
