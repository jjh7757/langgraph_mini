"""TransactionRepository의 JSON 파일 구현체.

Transaction은 고유 id가 없는 append-only 엔티티라 JsonListStore를 씀
(JsonAccountRepository의 {id: 레코드} 방식과 다름 — json_file_store 참고).
"""

from pathlib import Path

from ..json_file_store import JsonListStore
from .domain import Transaction


class JsonTransactionRepository:
    def __init__(self, path: str | Path = "data/transactions.json") -> None:
        self._store = JsonListStore(path)
        self._transactions: list[Transaction] = self._store.load()

    def save(self, transaction: Transaction) -> None:
        self._transactions.append(transaction)
        self._store.save_all(self._transactions)

    def find_by_account_id(self, account_id: str) -> list[Transaction]:
        return [
            transaction
            for transaction in self._transactions
            if transaction.account_id == account_id
        ]
