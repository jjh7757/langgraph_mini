"""AccountRepository protocol과 메모리 구현체.

TODO(직접 구현): InMemoryAccountRepository의 실제 로직.
DB 구현체(예: SqlAccountRepository)는 나중에 별도 파일(repository_sql.py)로 추가할 것 —
로직을 InMemoryAccountRepository로 먼저 검증한 뒤 교체.
"""

from typing import Protocol

from .domain import Account


class AccountRepository(Protocol):
    def find_by_id(self, account_id: str) -> Account: ...
    def find_all(self) -> list[Account]: ...
    def save(self, account: Account) -> None: ...


class InMemoryAccountRepository:
    """AccountRepository를 상속하지 않아도 됨 — 메서드 시그니처만 맞으면 protocol을 만족."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}

    def find_by_id(self, account_id: str) -> Account:
        """없으면 AccountNotFoundError."""
        raise NotImplementedError

    def find_all(self) -> list[Account]:
        raise NotImplementedError

    def save(self, account: Account) -> None:
        raise NotImplementedError
