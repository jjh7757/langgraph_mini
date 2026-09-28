"""ReissueRequestRepository의 JSON 파일 구현체."""

from pathlib import Path

from ..json_file_store import JsonFileStore
from .domain import ReissueRequest, ReissueRequestNotFoundError


class JsonReissueRequestRepository:
    def __init__(self, path: str | Path = "data/reissue_requests.json") -> None:
        self._store = JsonFileStore(path)
        self._requests: dict[str, ReissueRequest] = self._store.load()

    def find_by_id(self, request_id: str) -> ReissueRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise ReissueRequestNotFoundError(request_id)
        return request

    def find_by_card_id(self, card_id: str) -> list[ReissueRequest]:
        return [
            request for request in self._requests.values() if request.card_id == card_id
        ]

    def save(self, request: ReissueRequest) -> None:
        self._requests[request.request_id] = request
        self._store.save_all(self._requests)
