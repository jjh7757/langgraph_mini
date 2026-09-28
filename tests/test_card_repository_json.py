import pytest

from langgraph_mini.card.domain import Card, CardKind, CardNotFoundError, CardStatus
from langgraph_mini.card.repository_json import JsonCardRepository


def test_save_then_find_by_id(tmp_path):
    repo = JsonCardRepository(tmp_path / "cards.json")
    card = Card(card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK)

    repo.save(card)

    assert repo.find_by_id("c1") == card


def test_find_by_id_raises_when_not_found(tmp_path):
    repo = JsonCardRepository(tmp_path / "cards.json")

    with pytest.raises(CardNotFoundError):
        repo.find_by_id("no-such-card")


def test_find_by_account_id_returns_only_that_accounts_cards(tmp_path):
    repo = JsonCardRepository(tmp_path / "cards.json")
    card1 = Card(card_id="c1", account_id="a1", name="카드1", kind=CardKind.CHECK)
    card2 = Card(card_id="c2", account_id="a1", name="카드2", kind=CardKind.CREDIT)
    card3 = Card(card_id="c3", account_id="a2", name="카드3", kind=CardKind.CHECK)
    repo.save(card1)
    repo.save(card2)
    repo.save(card3)

    assert repo.find_by_account_id("a1") == [card1, card2]


def test_data_survives_reopening_the_repository(tmp_path):
    path = tmp_path / "cards.json"
    repo = JsonCardRepository(path)
    repo.save(
        Card(
            card_id="c1",
            account_id="a1",
            name="생활비 카드",
            kind=CardKind.CHECK,
            status=CardStatus.LOST,
        )
    )

    reopened = JsonCardRepository(path)

    card = reopened.find_by_id("c1")
    assert card.status is CardStatus.LOST
    assert card.kind is CardKind.CHECK
