"""CardRepository protocol과 메모리 구현체.

TODO(직접 구현): MemoryCardRepository의 실제 로직.
"""

from typing import Protocol

from .domain import Card


class CardRepository(Protocol):
    def find_by_id(self, card_id: str) -> Card: ...
    def find_by_account_id(self, account_id: str) -> list[Card]: ...
    def save(self, card: Card) -> None: ...


class MemoryCardRepository:
    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}

    def find_by_id(self, card_id: str) -> Card:
        """없으면 CardNotFoundError. AccountRepository.find_by_id와 같은 패턴."""
        raise NotImplementedError

    def find_by_account_id(self, account_id: str) -> list[Card]:
        raise NotImplementedError

    def save(self, card: Card) -> None:
        raise NotImplementedError
