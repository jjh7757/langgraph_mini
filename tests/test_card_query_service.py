from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.card.domain import Card, CardKind
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.services.query import DefaultCardQueryService


def _service():
    card_repo = MemoryCardRepository()
    account_repo = MemoryAccountRepository()
    return DefaultCardQueryService(card_repo, account_repo), card_repo, account_repo


def test_get_card_returns_card_by_id():
    service, card_repo, _ = _service()
    card = Card(card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK)
    card_repo.save(card)

    assert service.get_card("c1") == card


def test_get_cards_collects_cards_across_owners_accounts():
    service, card_repo, account_repo = _service()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))
    account_repo.save(Account(account_id="a2", owner_id="u1", nickname="비상금", balance=2000))
    account_repo.save(Account(account_id="a3", owner_id="u2", nickname="딴사람", balance=3000))
    card1 = Card(card_id="c1", account_id="a1", name="카드1", kind=CardKind.CHECK)
    card2 = Card(card_id="c2", account_id="a2", name="카드2", kind=CardKind.CREDIT)
    card3 = Card(card_id="c3", account_id="a3", name="카드3", kind=CardKind.CHECK)
    card_repo.save(card1)
    card_repo.save(card2)
    card_repo.save(card3)

    assert service.get_cards("u1") == [card1, card2]


def test_get_cards_returns_empty_list_when_owner_has_no_accounts():
    service, _, _ = _service()

    assert service.get_cards("no-such-owner") == []
