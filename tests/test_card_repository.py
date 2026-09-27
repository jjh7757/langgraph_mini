import pytest

from langgraph_mini.account.card_repository import MemoryCardRepository
from langgraph_mini.account.domain import Card, CardNotFoundError


def test_save_then_find_by_id():
    repo = MemoryCardRepository()
    card = Card(card_id="c1", account_id="a1", name="국민 체크카드")

    repo.save(card)

    assert repo.find_by_id("c1") == card


def test_find_by_id_raises_when_not_found():
    repo = MemoryCardRepository()

    with pytest.raises(CardNotFoundError):
        repo.find_by_id("no-such-card")


def test_find_by_account_id_returns_only_that_accounts_cards():
    repo = MemoryCardRepository()
    card1 = Card(card_id="c1", account_id="a1", name="카드1")
    card2 = Card(card_id="c2", account_id="a1", name="카드2")
    card3 = Card(card_id="c3", account_id="a2", name="카드3")
    repo.save(card1)
    repo.save(card2)
    repo.save(card3)

    assert repo.find_by_account_id("a1") == [card1, card2]
