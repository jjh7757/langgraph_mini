from datetime import date

import pytest

from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.billing.domain import Bill
from langgraph_mini.billing.repository import MemoryBillRepository
from langgraph_mini.card.domain import Card, CardKind, DeliveryAddress, ReissueRequest
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.reissue_request_repository import MemoryReissueRequestRepository
from langgraph_mini.orchestration.domain import NotOwnerError
from langgraph_mini.orchestration.ownership import (
    verify_account_owner,
    verify_bill_owner,
    verify_card_owner,
    verify_is_self,
    verify_reissue_request_owner,
)


def test_verify_account_owner_passes_for_owner():
    repo = MemoryAccountRepository()
    repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))

    verify_account_owner(repo, "a1", "u1")  # 예외 없이 통과


def test_verify_account_owner_raises_for_non_owner():
    repo = MemoryAccountRepository()
    repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))

    with pytest.raises(NotOwnerError):
        verify_account_owner(repo, "a1", "u2")


def test_verify_card_owner_passes_through_account():
    account_repo = MemoryAccountRepository()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))
    card_repo = MemoryCardRepository()
    card_repo.save(Card(card_id="c1", account_id="a1", name="카드", kind=CardKind.CHECK))

    verify_card_owner(card_repo, account_repo, "c1", "u1")


def test_verify_card_owner_raises_for_non_owner():
    account_repo = MemoryAccountRepository()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))
    card_repo = MemoryCardRepository()
    card_repo.save(Card(card_id="c1", account_id="a1", name="카드", kind=CardKind.CHECK))

    with pytest.raises(NotOwnerError):
        verify_card_owner(card_repo, account_repo, "c1", "u2")


def test_verify_reissue_request_owner_passes_through_card_and_account():
    account_repo = MemoryAccountRepository()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))
    card_repo = MemoryCardRepository()
    card_repo.save(Card(card_id="c1", account_id="a1", name="카드", kind=CardKind.CHECK))
    reissue_repo = MemoryReissueRequestRepository()
    reissue_repo.save(
        ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)
    )

    verify_reissue_request_owner(reissue_repo, card_repo, account_repo, "r1", "u1")


def test_verify_reissue_request_owner_raises_for_non_owner():
    account_repo = MemoryAccountRepository()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))
    card_repo = MemoryCardRepository()
    card_repo.save(Card(card_id="c1", account_id="a1", name="카드", kind=CardKind.CHECK))
    reissue_repo = MemoryReissueRequestRepository()
    reissue_repo.save(
        ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)
    )

    with pytest.raises(NotOwnerError):
        verify_reissue_request_owner(reissue_repo, card_repo, account_repo, "r1", "u2")


def test_verify_bill_owner_passes_for_owner():
    repo = MemoryBillRepository()
    repo.save(Bill(bill_id="b1", owner_id="u1", name="전기요금", amount=1000, due_date=date(2026, 1, 1)))

    verify_bill_owner(repo, "b1", "u1")


def test_verify_bill_owner_raises_for_non_owner():
    repo = MemoryBillRepository()
    repo.save(Bill(bill_id="b1", owner_id="u1", name="전기요금", amount=1000, due_date=date(2026, 1, 1)))

    with pytest.raises(NotOwnerError):
        verify_bill_owner(repo, "b1", "u2")


def test_verify_is_self_passes_when_same():
    verify_is_self("u1", "u1")


def test_verify_is_self_raises_when_different():
    with pytest.raises(NotOwnerError):
        verify_is_self("u1", "u2")
