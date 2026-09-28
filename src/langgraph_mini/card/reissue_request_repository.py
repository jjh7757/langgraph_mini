"""ReissueRequestRepository protocol과 메모리 구현체."""

from typing import Protocol

from .domain import ReissueRequest


class ReissueRequestRepository(Protocol):
    def find_by_id(self, request_id: str) -> ReissueRequest: ...
    def find_by_card_id(self, card_id: str) -> list[ReissueRequest]: ...
    def save(self, request: ReissueRequest) -> None: ...


class MemoryReissueRequestRepository:
    def __init__(self) -> None:
        self._requests: dict[str, ReissueRequest] = {}

    def find_by_id(self, request_id: str) -> ReissueRequest:
        """없으면 ReissueRequestNotFoundError. CardRepository.find_by_id와 같은 패턴."""
        ...

    def find_by_card_id(self, card_id: str) -> list[ReissueRequest]:
        """없으면 빈 리스트(예외 아님) — CardRepository.find_by_account_id와 같은 패턴."""
        ...

    def save(self, request: ReissueRequest) -> None:
        ...
