from datetime import date

import pytest

from langgraph_mini.account.domain import (
    Account,
    InsufficientBalanceError,
    TransactionType,
)
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository
from langgraph_mini.billing.domain import (
    Bill,
    BillAlreadyPaidError,
    BillNotFoundError,
    BillStatus,
)
from langgraph_mini.billing.repository import MemoryBillRepository
from langgraph_mini.billing.services.pay import BillPaymentOutcome, DefaultBillPaymentService


def _bill(bill_id, amount, due_date, status=BillStatus.UNPAID, owner_id="u1"):
    return Bill(
        bill_id=bill_id,
        owner_id=owner_id,
        name="청구서",
        amount=amount,
        due_date=due_date,
        status=status,
    )


def _service_with(bills, balance=100000):
    bill_repo = MemoryBillRepository()
    for bill in bills:
        bill_repo.save(bill)
    account_repo = MemoryAccountRepository()
    account_repo.save(
        Account(account_id="a1", owner_id="u1", nickname="생활비", balance=balance)
    )
    tx_repo = MemoryTransactionRepository()
    return DefaultBillPaymentService(bill_repo, account_repo, tx_repo), bill_repo, account_repo, tx_repo


def test_pay_bill_withdraws_and_marks_paid():
    service, bill_repo, account_repo, tx_repo = _service_with(
        [_bill("b1", 30000, date(2026, 1, 31))], balance=100000
    )

    result = service.pay_bill("b1", "a1")

    assert result.bill.status is BillStatus.PAID
    assert result.transaction.amount == 30000
    assert result.transaction.transaction_type is TransactionType.BILL_PAYMENT
    assert result.transaction.bill_id == "b1"
    assert account_repo.find_by_id("a1").balance == 70000
    assert bill_repo.find_by_id("b1").status is BillStatus.PAID
    assert tx_repo.find_by_account_id("a1") == [result.transaction]


def test_pay_bill_raises_when_already_paid():
    service, _, account_repo, _ = _service_with(
        [_bill("b1", 30000, date(2026, 1, 31), status=BillStatus.PAID)]
    )

    with pytest.raises(BillAlreadyPaidError):
        service.pay_bill("b1", "a1")

    assert account_repo.find_by_id("a1").balance == 100000  # 계좌는 안 건드림


def test_pay_bill_raises_when_insufficient_balance():
    service, bill_repo, account_repo, _ = _service_with(
        [_bill("b1", 30000, date(2026, 1, 31))], balance=10000
    )

    with pytest.raises(InsufficientBalanceError):
        service.pay_bill("b1", "a1")

    assert bill_repo.find_by_id("b1").status is BillStatus.UNPAID  # 청구서 상태 그대로
    assert account_repo.find_by_id("a1").balance == 10000


def test_pay_bill_allows_payment_past_due_date_without_penalty():
    service, _, account_repo, _ = _service_with(
        [_bill("b1", 30000, date(2020, 1, 1))], balance=100000  # 훨씬 지난 기한
    )

    result = service.pay_bill("b1", "a1")

    assert result.transaction.amount == 30000  # 연체료 없이 그대로
    assert account_repo.find_by_id("a1").balance == 70000


def test_pay_bills_processes_in_due_date_order_and_completes_all():
    bills = [
        _bill("b2", 20000, date(2026, 2, 1)),
        _bill("b1", 10000, date(2026, 1, 1)),
    ]
    service, bill_repo, account_repo, _ = _service_with(bills, balance=100000)

    attempts = service.pay_bills("a1", ["b1", "b2"])

    assert [a.bill_id for a in attempts] == ["b1", "b2"]
    assert all(a.outcome is BillPaymentOutcome.COMPLETED for a in attempts)
    assert bill_repo.find_by_id("b1").status is BillStatus.PAID
    assert bill_repo.find_by_id("b2").status is BillStatus.PAID
    assert account_repo.find_by_id("a1").balance == 70000


def test_pay_bills_marks_insufficient_balance_as_failed_and_continues():
    bills = [
        _bill("b1", 10000, date(2026, 1, 1)),
        _bill("b2", 200000, date(2026, 1, 2)),  # 잔액 부족
        _bill("b3", 5000, date(2026, 1, 3)),
    ]
    service, bill_repo, account_repo, _ = _service_with(bills, balance=20000)

    attempts = service.pay_bills("a1", ["b1", "b2", "b3"])

    outcomes = {a.bill_id: a.outcome for a in attempts}
    assert outcomes["b1"] is BillPaymentOutcome.COMPLETED
    assert outcomes["b2"] is BillPaymentOutcome.FAILED
    assert outcomes["b3"] is BillPaymentOutcome.COMPLETED
    assert bill_repo.find_by_id("b2").status is BillStatus.UNPAID  # 미납 유지
    assert account_repo.find_by_id("a1").balance == 5000  # 10000(b1) + 5000(b3) 차감


def test_pay_bills_treats_already_paid_bill_as_completed_without_reprocessing():
    bills = [
        _bill("b1", 10000, date(2026, 1, 1), status=BillStatus.PAID),
        _bill("b2", 5000, date(2026, 1, 2)),
    ]
    service, _, account_repo, _ = _service_with(bills, balance=100000)

    attempts = service.pay_bills("a1", ["b1", "b2"])

    b1_attempt = next(a for a in attempts if a.bill_id == "b1")
    assert b1_attempt.outcome is BillPaymentOutcome.COMPLETED
    assert b1_attempt.transaction is None  # 재처리 안 했으니 거래 기록도 새로 안 생김
    assert account_repo.find_by_id("a1").balance == 95000  # b2만 차감


def test_pay_bills_raises_when_any_bill_id_not_found():
    service, _, _, _ = _service_with([_bill("b1", 10000, date(2026, 1, 1))])

    with pytest.raises(BillNotFoundError):
        service.pay_bills("a1", ["b1", "no-such-bill"])


def test_pay_bills_stops_and_marks_unprocessed_on_storage_failure():
    bills = [
        _bill("b1", 10000, date(2026, 1, 1)),
        _bill("b2", 5000, date(2026, 1, 2)),
        _bill("b3", 5000, date(2026, 1, 3)),
    ]
    service, bill_repo, account_repo, _ = _service_with(bills, balance=100000)

    original_save = bill_repo.save
    call_count = {"n": 0}

    def flaky_save(bill):
        call_count["n"] += 1
        if call_count["n"] == 2:  # b2 저장 시점에 실패
            raise RuntimeError("storage failure")
        original_save(bill)

    bill_repo.save = flaky_save

    attempts = service.pay_bills("a1", ["b1", "b2", "b3"])

    outcomes = {a.bill_id: a.outcome for a in attempts}
    assert outcomes["b1"] is BillPaymentOutcome.COMPLETED
    assert outcomes["b2"] is BillPaymentOutcome.UNPROCESSED
    assert outcomes["b3"] is BillPaymentOutcome.UNPROCESSED

    # b1은 이미 저장 성공했으니 유지, b2/b3는 정말로 미반영(미납 그대로)
    assert bill_repo.find_by_id("b1").status is BillStatus.PAID
    assert bill_repo.find_by_id("b2").status is BillStatus.UNPAID
    assert bill_repo.find_by_id("b3").status is BillStatus.UNPAID
    assert account_repo.find_by_id("a1").balance == 90000  # b1(10000)만 차감
