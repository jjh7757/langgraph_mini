"""BillRepository의 JSON 파일 구현체."""

from pathlib import Path

from ..json_file_store import JsonFileStore
from .domain import Bill, BillNotFoundError


class JsonBillRepository:
    def __init__(self, path: str | Path = "data/bills.json") -> None:
        self._store = JsonFileStore(path)
        self._bills: dict[str, Bill] = self._store.load()

    def find_by_id(self, bill_id: str) -> Bill:
        bill = self._bills.get(bill_id)
        if bill is None:
            raise BillNotFoundError(bill_id)
        return bill

    def find_by_owner_id(self, owner_id: str) -> list[Bill]:
        return [bill for bill in self._bills.values() if bill.owner_id == owner_id]

    def save(self, bill: Bill) -> None:
        self._bills[bill.bill_id] = bill
        self._store.save_all(self._bills)
