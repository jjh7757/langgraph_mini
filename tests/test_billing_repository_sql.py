from datetime import date, timedelta

import pytest

from langgraph_mini.billing.domain import Bill, BillNotFoundError, BillStatus
from langgraph_mini.billing.repository_sql import SqlBillRepository


def test_save_then_find_by_id(pg_conn):
    repo = SqlBillRepository()
    bill = Bill(
        bill_id="b1", owner_id="u1", name="전기요금", amount=45000,
        due_date=date.today() + timedelta(days=10),
    )

    repo.save(bill)

    assert repo.find_by_id("b1") == bill


def test_find_by_id_raises_when_not_found(pg_conn):
    repo = SqlBillRepository()

    with pytest.raises(BillNotFoundError):
        repo.find_by_id("no-such-bill")


def test_find_by_owner_id_returns_only_that_owners_bills(pg_conn):
    repo = SqlBillRepository()
    bill1 = Bill(bill_id="b1", owner_id="u1", name="전기요금", amount=45000, due_date=date.today())
    bill2 = Bill(bill_id="b2", owner_id="u2", name="가스요금", amount=30000, due_date=date.today())
    repo.save(bill1)
    repo.save(bill2)

    assert repo.find_by_owner_id("u1") == [bill1]


def test_pay_persists_status_change(pg_conn):
    repo = SqlBillRepository()
    bill = Bill(bill_id="b1", owner_id="u1", name="전기요금", amount=45000, due_date=date.today())
    repo.save(bill)

    bill.pay()
    repo.save(bill)

    assert repo.find_by_id("b1").status is BillStatus.PAID
