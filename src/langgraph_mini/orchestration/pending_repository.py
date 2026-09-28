"""PendingRepository protocol과 메모리 구현체."""

from typing import Protocol

from .domain import PendingRequest, PendingRequestNotFoundError


class PendingRepository(Protocol):
    def find_by_id(self, request_id: str) -> PendingRequest: ...
    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]: ...
    def save(self, request: PendingRequest) -> None: ...


class MemoryPendingRepository:
    def __init__(self) -> None:
        self._requests: dict[str, PendingRequest] = {}

    def find_by_id(self, request_id: str) -> PendingRequest:
        """없으면 PendingRequestNotFoundError. CardRepository.find_by_id와 같은 패턴."""
        request = self._requests.get(request_id)
        if request is None:
            raise PendingRequestNotFoundError(request_id)
        return request

    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]:
        """없으면 빈 리스트(예외 아님)."""
        return [
            request for request in self._requests.values() if request.thread_id == thread_id
        ]

    def save(self, request: PendingRequest) -> None:
        self._requests[request.request_id] = request
