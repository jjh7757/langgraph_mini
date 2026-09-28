"""BillRepository protocol과 메모리 구현체."""

from typing import Protocol

from .domain import Bill, BillNotFoundError


class BillRepository(Protocol):
    def find_by_id(self, bill_id: str) -> Bill: ...
    def find_by_owner_id(self, owner_id: str) -> list[Bill]: ...
    def save(self, bill: Bill) -> None: ...


class MemoryBillRepository:
    def __init__(self) -> None:
        self._bills: dict[str, Bill] = {}

    def find_by_id(self, bill_id: str) -> Bill:
        """없으면 BillNotFoundError. AccountRepository.find_by_id와 같은 패턴."""
        bill = self._bills.get(bill_id)
        if bill is None:
            raise BillNotFoundError(bill_id)
        return bill

    def find_by_owner_id(self, owner_id: str) -> list[Bill]:
        """owner_id가 일치하는 청구서 전부 (없으면 빈 리스트, 예외 아님)."""
        return [bill for bill in self._bills.values() if bill.owner_id == owner_id]

    def save(self, bill: Bill) -> None:
        self._bills[bill.bill_id] = bill
