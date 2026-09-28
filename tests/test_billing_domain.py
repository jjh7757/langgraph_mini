from datetime import date

import pytest

from langgraph_mini.billing.domain import Bill, BillAlreadyPaidError, BillStatus


def _bill(status: BillStatus = BillStatus.UNPAID) -> Bill:
    return Bill(
        bill_id="b1",
        owner_id="u1",
        name="전기요금",
        amount=30000,
        due_date=date(2026, 1, 31),
        status=status,
    )


def test_pay_changes_status_to_paid():
    bill = _bill(BillStatus.UNPAID)
    bill.pay()
    assert bill.status is BillStatus.PAID


def test_pay_raises_when_already_paid():
    bill = _bill(BillStatus.PAID)
    with pytest.raises(BillAlreadyPaidError):
        bill.pay()
