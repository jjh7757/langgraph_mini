"""TransactionRepository protocol과 메모리 구현체.

TODO(직접 구현): MemoryTransactionRepository의 실제 로직.
날짜/금액/유형 필터링은 여기서 하지 않음 — Repository는 순수 저장/조회만 담당하고,
필터링·정렬(최근순)은 AccountQueryService(서비스 계층)의 책임.
"""

from typing import Protocol

from .domain import Transaction


class TransactionRepository(Protocol):
    def save(self, transaction: Transaction) -> None: ...
    def find_by_account_id(self, account_id: str) -> list[Transaction]: ...


class MemoryTransactionRepository:
    def __init__(self) -> None:
        self._transactions: list[Transaction] = []

    def save(self, transaction: Transaction) -> None:
        """새 거래 내역을 추가로 저장 (Account와 달리 id로 덮어쓰는 게 아니라
        매번 새 레코드를 append)."""
        raise NotImplementedError

    def find_by_account_id(self, account_id: str) -> list[Transaction]:
        """account_id가 일치하는 거래 내역 전부 (없으면 빈 리스트)."""
        raise NotImplementedError
