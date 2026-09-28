import pytest

from langgraph_mini.card.domain import (
    Card,
    CardAlreadyLostError,
    CardKind,
    CardNotLockedError,
    CardNotUsableError,
    CardStatus,
)
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.services.status import DefaultCardStatusService


def _service_with(*cards: Card):
    repo = MemoryCardRepository()
    for card in cards:
        repo.save(card)
    return DefaultCardStatusService(repo), repo


def _card(status: CardStatus = CardStatus.USABLE) -> Card:
    return Card(card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK, status=status)


def test_block_as_lost_persists_status():
    service, repo = _service_with(_card(CardStatus.USABLE))

    result = service.block_as_lost("c1")

    assert result.status is CardStatus.LOST
    assert repo.find_by_id("c1").status is CardStatus.LOST


def test_block_as_lost_raises_when_already_lost():
    service, _ = _service_with(_card(CardStatus.LOST))

    with pytest.raises(CardAlreadyLostError):
        service.block_as_lost("c1")


def test_lock_temporarily_persists_status():
    service, repo = _service_with(_card(CardStatus.USABLE))

    result = service.lock_temporarily("c1")

    assert result.status is CardStatus.LOCKED
    assert repo.find_by_id("c1").status is CardStatus.LOCKED


def test_lock_temporarily_raises_when_lost():
    service, _ = _service_with(_card(CardStatus.LOST))

    with pytest.raises(CardNotUsableError):
        service.lock_temporarily("c1")


def test_unlock_persists_status():
    service, repo = _service_with(_card(CardStatus.LOCKED))

    result = service.unlock("c1")

    assert result.status is CardStatus.USABLE
    assert repo.find_by_id("c1").status is CardStatus.USABLE


def test_unlock_raises_when_lost():
    service, _ = _service_with(_card(CardStatus.LOST))

    with pytest.raises(CardNotLockedError):
        service.unlock("c1")
