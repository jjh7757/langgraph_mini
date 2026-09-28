from datetime import date

import pytest

from langgraph_mini.billing.domain import Bill, BillNotFoundError, BillStatus
from langgraph_mini.billing.repository_json import JsonBillRepository


def _bill(bill_id: str, owner_id: str, due_date: date = date(2026, 1, 31)) -> Bill:
    return Bill(
        bill_id=bill_id, owner_id=owner_id, name="전기요금", amount=10000, due_date=due_date
    )


def test_save_then_find_by_id(tmp_path):
    repo = JsonBillRepository(tmp_path / "bills.json")
    bill = _bill("b1", "u1")

    repo.save(bill)

    assert repo.find_by_id("b1") == bill


def test_find_by_id_raises_when_not_found(tmp_path):
    repo = JsonBillRepository(tmp_path / "bills.json")

    with pytest.raises(BillNotFoundError):
        repo.find_by_id("no-such-bill")


def test_find_by_owner_id_returns_only_that_owners_bills(tmp_path):
    repo = JsonBillRepository(tmp_path / "bills.json")
    bill1 = _bill("b1", "u1")
    bill2 = _bill("b2", "u2")
    repo.save(bill1)
    repo.save(bill2)

    assert repo.find_by_owner_id("u1") == [bill1]


def test_data_survives_reopening_the_repository(tmp_path):
    path = tmp_path / "bills.json"
    repo = JsonBillRepository(path)
    bill = _bill("b1", "u1", due_date=date(2020, 1, 1))
    bill.status = BillStatus.PAID
    repo.save(bill)

    reopened = JsonBillRepository(path)

    reloaded = reopened.find_by_id("b1")
    assert reloaded.status is BillStatus.PAID
    assert reloaded.due_date == date(2020, 1, 1)
