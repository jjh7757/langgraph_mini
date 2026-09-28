"""CompletedRequestRepository protocol과 메모리 구현체.

멱등성(request_id 재사용 시 재실행 안 함)과 후속 결과 조회("아까 이체가 됐어?")의
근거가 되는 저장소. PendingRepo와 달리 find_by_request_id가 없으면 예외가 아니라
None을 반환함 — "이 request_id는 아직 완료된 적 없음"은 정상적인 경우라서(멱등성
체크마다 예외 처리를 하게 만들면 번거로움).
"""

from typing import Protocol

from .domain import PendingRequest


class CompletedRequestRepository(Protocol):
    def find_by_request_id(self, request_id: str) -> PendingRequest | None: ...
    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]: ...
    def save(self, request: PendingRequest) -> None: ...


class MemoryCompletedRequestRepository:
    def __init__(self) -> None:
        self._requests: dict[str, PendingRequest] = {}

    def find_by_request_id(self, request_id: str) -> PendingRequest | None:
        return self._requests.get(request_id)

    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]:
        return [
            request for request in self._requests.values() if request.thread_id == thread_id
        ]

    def save(self, request: PendingRequest) -> None:
        self._requests[request.request_id] = request
