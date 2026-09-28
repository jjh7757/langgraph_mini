"""CardRepository의 JSON 파일 구현체."""

from pathlib import Path

from ..json_file_store import JsonFileStore
from .domain import Card, CardNotFoundError


class JsonCardRepository:
    def __init__(self, path: str | Path = "data/cards.json") -> None:
        self._store = JsonFileStore(path)
        self._cards: dict[str, Card] = self._store.load()

    def find_by_id(self, card_id: str) -> Card:
        card = self._cards.get(card_id)
        if card is None:
            raise CardNotFoundError(card_id)
        return card

    def find_by_account_id(self, account_id: str) -> list[Card]:
        return [card for card in self._cards.values() if card.account_id == account_id]

    def save(self, card: Card) -> None:
        self._cards[card.card_id] = card
        self._store.save_all(self._cards)
