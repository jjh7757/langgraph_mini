"""PendingRepository의 JSON 파일 구현체.

재시작·장애 복구가 이 저장소에 실제로 의존함(오케스트레이션_설계.md 3절) — 프로세스가
꺼져도 대기 중이던 요청이 파일에 남아있어야 get_pending(thread_id)로 다시 찾을 수 있음.
"""

from pathlib import Path

from ..json_file_store import JsonFileStore
from .domain import PendingRequest, PendingRequestNotFoundError


class JsonPendingRepository:
    def __init__(self, path: str | Path = "data/pending_requests.json") -> None:
        self._store = JsonFileStore(path)
        self._requests: dict[str, PendingRequest] = self._store.load()

    def find_by_id(self, request_id: str) -> PendingRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise PendingRequestNotFoundError(request_id)
        return request

    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]:
        return [
            request for request in self._requests.values() if request.thread_id == thread_id
        ]

    def save(self, request: PendingRequest) -> None:
        self._requests[request.request_id] = request
        self._store.save_all(self._requests)
