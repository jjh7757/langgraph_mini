"""청구서 조회 서비스."""

from typing import Protocol

from ..domain import Bill, BillStatus
from ..repository import BillRepository


class BillingQueryService(Protocol):
    def get_unpaid_bills(self, owner_id: str) -> list[Bill]: ...


class DefaultBillingQueryService:
    def __init__(self, bill_repo: BillRepository) -> None:
        self._bill_repo = bill_repo

    def get_unpaid_bills(self, owner_id: str) -> list[Bill]:
        """owner_id의 청구서 중 UNPAID만 골라 납기일(due_date) 오름차순으로 정렬해 반환."""
        bills = [
            bill
            for bill in self._bill_repo.find_by_owner_id(owner_id)
            if bill.status is BillStatus.UNPAID
        ]
        bills.sort(key=lambda bill: bill.due_date)
        return bills
