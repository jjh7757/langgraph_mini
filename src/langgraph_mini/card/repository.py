"""CardRepository protocol과 메모리 구현체."""

from typing import Protocol

from .domain import Card, CardNotFoundError


class CardRepository(Protocol):
    def find_by_id(self, card_id: str) -> Card: ...
    def find_by_account_id(self, account_id: str) -> list[Card]: ...
    def save(self, card: Card) -> None: ...


class MemoryCardRepository:
    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}

    def find_by_id(self, card_id: str) -> Card:
        """없으면 CardNotFoundError. AccountRepository.find_by_id와 같은 패턴."""
        card = self._cards.get(card_id)
        if card is None:
            raise CardNotFoundError(card_id)
        return card

    def find_by_account_id(self, account_id: str) -> list[Card]:
        return [card for card in self._cards.values() if card.account_id == account_id]

    def save(self, card: Card) -> None:
        self._cards[card.card_id] = card
