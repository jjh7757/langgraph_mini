"""CompletedRequestRepository의 JSON 파일 구현체.

멱등성(request_id 재사용 시 재실행 안 함)과 후속 결과 조회의 진짜 근거 — 이것도
재시작에도 살아남아야 해서 JSON 파일로 둠(나중에 Postgres로 교체 예정).
"""

from pathlib import Path

from ..json_file_store import JsonFileStore
from .domain import PendingRequest


class JsonCompletedRequestRepository:
    def __init__(self, path: str | Path = "data/completed_requests.json") -> None:
        self._store = JsonFileStore(path)
        self._requests: dict[str, PendingRequest] = self._store.load()

    def find_by_request_id(self, request_id: str) -> PendingRequest | None:
        return self._requests.get(request_id)

    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]:
        return [
            request for request in self._requests.values() if request.thread_id == thread_id
        ]

    def save(self, request: PendingRequest) -> None:
        self._requests[request.request_id] = request
        self._store.save_all(self._requests)
