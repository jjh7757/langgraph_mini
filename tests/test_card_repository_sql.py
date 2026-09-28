import pytest

from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository_sql import SqlAccountRepository
from langgraph_mini.card.domain import (
    Card,
    CardKind,
    CardNotFoundError,
    CardStatus,
    DeliveryAddress,
    ReissueRequest,
    ReissueRequestNotFoundError,
    ReissueStatus,
)
from langgraph_mini.card.reissue_request_repository_sql import SqlReissueRequestRepository
from langgraph_mini.card.repository_sql import SqlCardRepository


def _seed_account(account_id="a1"):
    SqlAccountRepository().save(
        Account(account_id=account_id, owner_id="u1", nickname="생활비", balance=1000)
    )


def test_save_then_find_by_id(pg_conn):
    _seed_account()
    repo = SqlCardRepository()
    card = Card(card_id="c1", account_id="a1", name="체크카드", kind=CardKind.CHECK)

    repo.save(card)

    assert repo.find_by_id("c1") == card


def test_find_by_id_raises_when_not_found(pg_conn):
    repo = SqlCardRepository()

    with pytest.raises(CardNotFoundError):
        repo.find_by_id("no-such-card")


def test_status_transition_persists(pg_conn):
    _seed_account()
    repo = SqlCardRepository()
    card = Card(card_id="c1", account_id="a1", name="체크카드", kind=CardKind.CHECK)
    repo.save(card)

    card.block_as_lost()
    repo.save(card)

    assert repo.find_by_id("c1").status is CardStatus.LOST


def test_find_by_account_id_filters(pg_conn):
    _seed_account("a1")
    _seed_account("a2")
    repo = SqlCardRepository()
    card1 = Card(card_id="c1", account_id="a1", name="체크카드", kind=CardKind.CHECK)
    card2 = Card(card_id="c2", account_id="a2", name="신용카드", kind=CardKind.CREDIT)
    repo.save(card1)
    repo.save(card2)

    assert repo.find_by_account_id("a1") == [card1]


def test_reissue_request_round_trip(pg_conn):
    _seed_account()
    SqlCardRepository().save(Card(card_id="c1", account_id="a1", name="체크카드", kind=CardKind.CHECK))
    repo = SqlReissueRequestRepository()
    request = ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)

    repo.save(request)

    assert repo.find_by_id("r1") == request
    assert repo.find_by_card_id("c1") == [request]


def test_reissue_request_find_by_id_raises_when_not_found(pg_conn):
    repo = SqlReissueRequestRepository()

    with pytest.raises(ReissueRequestNotFoundError):
        repo.find_by_id("no-such-request")


def test_reissue_request_status_change_persists(pg_conn):
    _seed_account()
    SqlCardRepository().save(Card(card_id="c1", account_id="a1", name="체크카드", kind=CardKind.CHECK))
    repo = SqlReissueRequestRepository()
    request = ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)
    repo.save(request)

    request.cancel()
    repo.save(request)

    assert repo.find_by_id("r1").status is ReissueStatus.CANCELLED
