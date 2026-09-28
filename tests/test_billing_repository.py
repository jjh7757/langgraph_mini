from datetime import date

import pytest

from langgraph_mini.billing.domain import Bill, BillNotFoundError
from langgraph_mini.billing.repository import MemoryBillRepository


def _bill(bill_id: str, owner_id: str, due_date: date = date(2026, 1, 31)) -> Bill:
    return Bill(
        bill_id=bill_id, owner_id=owner_id, name="전기요금", amount=10000, due_date=due_date
    )


def test_save_then_find_by_id():
    repo = MemoryBillRepository()
    bill = _bill("b1", "u1")

    repo.save(bill)

    assert repo.find_by_id("b1") == bill


def test_find_by_id_raises_when_not_found():
    repo = MemoryBillRepository()

    with pytest.raises(BillNotFoundError):
        repo.find_by_id("no-such-bill")


def test_find_by_owner_id_returns_only_that_owners_bills():
    repo = MemoryBillRepository()
    bill1 = _bill("b1", "u1")
    bill2 = _bill("b2", "u1")
    bill3 = _bill("b3", "u2")
    repo.save(bill1)
    repo.save(bill2)
    repo.save(bill3)

    assert repo.find_by_owner_id("u1") == [bill1, bill2]
