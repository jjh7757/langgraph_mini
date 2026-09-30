from datetime import date

import pytest

from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository
from langgraph_mini.agent.assembly import assemble_orchestration
from langgraph_mini.billing.domain import Bill
from langgraph_mini.billing.repository import MemoryBillRepository
from langgraph_mini.card.domain import Card, CardKind, CardStatus
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.reissue_request_repository import MemoryReissueRequestRepository
from langgraph_mini.orchestration.completed_repository import MemoryCompletedRequestRepository
from langgraph_mini.orchestration.domain import (
    ActionNotRegisteredError,
    MissingParamsError,
    NotOwnerError,
    PendingRequestNotFoundError,
    PendingRequestNotPendingError,
    PendingStatus,
)
from langgraph_mini.orchestration.pending_repository import MemoryPendingRepository


def _build():
    account_repo = MemoryAccountRepository()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=100000))
    account_repo.save(Account(account_id="a2", owner_id="u2", nickname="딴사람 계좌", balance=5000))
    transaction_repo = MemoryTransactionRepository()

    card_repo = MemoryCardRepository()
    card_repo.save(Card(card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK))
    reissue_repo = MemoryReissueRequestRepository()

    bill_repo = MemoryBillRepository()
    bill_repo.save(Bill(bill_id="b1", owner_id="u1", name="전기요금", amount=30000, due_date=date(2026, 1, 31)))


    pending_repo = MemoryPendingRepository()
    completed_repo = MemoryCompletedRequestRepository()
    orchestration = assemble_orchestration(
        account_repo=account_repo,
        transaction_repo=transaction_repo,
        card_repo=card_repo,
        reissue_repo=reissue_repo,
        bill_repo=bill_repo,
        pending_repo=pending_repo,
        completed_repo=completed_repo,
    )

    return orchestration, {
        "account_repo": account_repo,
        "card_repo": card_repo,
        "bill_repo": bill_repo,
        "pending_repo": pending_repo,
        "completed_repo": completed_repo,
    }


# ── query() ──────────────────────────────────────────────────────────


def test_query_returns_result_when_owner_matches():
    orchestration, _ = _build()

    account = orchestration.query("account.get_account", {"account_id": "a1"}, "u1")

    assert account.balance == 100000


def test_query_raises_not_owner_error():
    orchestration, _ = _build()

    with pytest.raises(NotOwnerError):
        orchestration.query("account.get_account", {"account_id": "a1"}, "u2")


def test_query_raises_missing_params_error():
    orchestration, _ = _build()

    with pytest.raises(MissingParamsError):
        orchestration.query("account.get_account", {}, "u1")


def test_query_raises_action_not_registered_error():
    orchestration, _ = _build()

    with pytest.raises(ActionNotRegisteredError):
        orchestration.query("no.such.action", {}, "u1")


# ── propose() ────────────────────────────────────────────────────────


def test_propose_creates_pending_request():
    orchestration, ctx = _build()

    request = orchestration.propose(
        "card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1"
    )

    assert request.status is PendingStatus.PENDING
    assert ctx["pending_repo"].find_by_id("r1") == request


def test_propose_raises_not_owner_error_and_does_not_create_pending():
    orchestration, ctx = _build()

    with pytest.raises(NotOwnerError):
        orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u2", "t1", "r1")

    with pytest.raises(PendingRequestNotFoundError):
        ctx["pending_repo"].find_by_id("r1")


def test_propose_returns_same_pending_when_called_again_before_approval():
    orchestration, _ = _build()

    first = orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")
    second = orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")

    assert first is second or first == second


def test_propose_is_idempotent_after_approval():
    orchestration, _ = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")
    orchestration.approve("r1")

    # 같은 request_id로 다시 propose해도 완료된 결과를 그대로 돌려줌(재실행 안 함)
    again = orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")

    assert again.status is PendingStatus.EXECUTED


# ── approve() ────────────────────────────────────────────────────────


def test_approve_executes_action_and_marks_executed():
    orchestration, ctx = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")

    result = orchestration.approve("r1")

    assert result.success is True
    assert result.value.status is CardStatus.LOST
    assert ctx["card_repo"].find_by_id("c1").status is CardStatus.LOST
    assert ctx["pending_repo"].find_by_id("r1").status is PendingStatus.EXECUTED
    assert ctx["completed_repo"].find_by_request_id("r1").status is PendingStatus.EXECUTED


def test_approve_marks_failed_and_returns_structured_error_on_domain_exception():
    orchestration, ctx = _build()
    orchestration.propose(
        "account.transfer", {"from_id": "a1", "to_id": "a2", "amount": 999999}, "u1", "t1", "r1"
    )

    result = orchestration.approve("r1")

    assert result.success is False
    assert result.error_type == "InsufficientBalanceError"
    assert ctx["pending_repo"].find_by_id("r1").status is PendingStatus.FAILED
    assert ctx["account_repo"].find_by_id("a1").balance == 100000  # 안 바뀜


def test_approve_raises_when_not_pending():
    orchestration, _ = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")
    orchestration.approve("r1")

    with pytest.raises(PendingRequestNotPendingError):
        orchestration.approve("r1")


def test_approve_raises_when_request_not_found():
    orchestration, _ = _build()

    with pytest.raises(PendingRequestNotFoundError):
        orchestration.approve("no-such-request")


# ── reject() ─────────────────────────────────────────────────────────


def test_reject_marks_rejected_and_does_not_execute():
    orchestration, ctx = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")

    request = orchestration.reject("r1")

    assert request.status is PendingStatus.REJECTED
    assert ctx["card_repo"].find_by_id("c1").status is CardStatus.USABLE  # 안 바뀜
    assert ctx["completed_repo"].find_by_request_id("r1").status is PendingStatus.REJECTED


def test_reject_raises_when_not_pending():
    orchestration, _ = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")
    orchestration.reject("r1")

    with pytest.raises(PendingRequestNotPendingError):
        orchestration.reject("r1")


# ── revise() ─────────────────────────────────────────────────────────


def test_revise_merges_params_and_keeps_pending():
    orchestration, ctx = _build()
    orchestration.propose(
        "account.transfer", {"from_id": "a1", "to_id": "a2", "amount": 100000}, "u1", "t1", "r1"
    )

    revised = orchestration.revise("r1", {"amount": 50000}, "u1")

    assert revised.status is PendingStatus.PENDING
    assert revised.params == {"from_id": "a1", "to_id": "a2", "amount": 50000}
    assert ctx["pending_repo"].find_by_id("r1").params["amount"] == 50000


def test_revise_raises_when_not_pending():
    orchestration, _ = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")
    orchestration.approve("r1")

    with pytest.raises(PendingRequestNotPendingError):
        orchestration.revise("r1", {"card_id": "c1"}, "u1")


def test_revise_reverifies_ownership_with_merged_params():
    orchestration, _ = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")

    with pytest.raises(NotOwnerError):
        orchestration.revise("r1", {"card_id": "c1"}, "u2")


# ── get_pending() / get_history() ───────────────────────────────────


def test_get_pending_returns_only_pending_for_thread():
    orchestration, _ = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")
    orchestration.propose(
        "billing.pay_bill", {"bill_id": "b1", "account_id": "a1"}, "u1", "t1", "r2"
    )
    orchestration.approve("r2")  # r2는 종결되니 get_pending에서 빠져야 함

    pending = orchestration.get_pending("t1")

    assert [p.request_id for p in pending] == ["r1"]


def test_get_pending_returns_empty_list_for_unknown_thread():
    orchestration, _ = _build()

    assert orchestration.get_pending("no-such-thread") == []


def test_get_history_returns_resolved_requests_for_thread():
    orchestration, _ = _build()
    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "r1")
    orchestration.approve("r1")

    history = orchestration.get_history("t1")

    assert len(history) == 1
    assert history[0].status is PendingStatus.EXECUTED
    assert history[0].result.success is True
