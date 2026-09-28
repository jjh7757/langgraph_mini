from datetime import date

from langgraph_mini.billing.domain import Bill, BillStatus
from langgraph_mini.billing.repository import MemoryBillRepository
from langgraph_mini.billing.services.query import DefaultBillingQueryService


def _service_with(*bills: Bill):
    repo = MemoryBillRepository()
    for bill in bills:
        repo.save(bill)
    return DefaultBillingQueryService(repo)


def test_get_unpaid_bills_excludes_paid():
    unpaid = Bill(
        bill_id="b1", owner_id="u1", name="전기요금", amount=10000,
        due_date=date(2026, 2, 1), status=BillStatus.UNPAID,
    )
    paid = Bill(
        bill_id="b2", owner_id="u1", name="수도요금", amount=5000,
        due_date=date(2026, 1, 1), status=BillStatus.PAID,
    )
    service = _service_with(unpaid, paid)

    assert service.get_unpaid_bills("u1") == [unpaid]


def test_get_unpaid_bills_sorted_by_due_date_ascending():
    later = Bill(
        bill_id="b1", owner_id="u1", name="전기요금", amount=10000, due_date=date(2026, 3, 1)
    )
    earlier = Bill(
        bill_id="b2", owner_id="u1", name="수도요금", amount=5000, due_date=date(2026, 1, 1)
    )
    service = _service_with(later, earlier)

    assert service.get_unpaid_bills("u1") == [earlier, later]


def test_get_unpaid_bills_returns_empty_list_when_none():
    service = _service_with()

    assert service.get_unpaid_bills("u1") == []
