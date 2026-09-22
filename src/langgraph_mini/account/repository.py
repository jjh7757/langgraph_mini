"""AccountRepository protocol과 메모리 구현체.

TODO(직접 구현): InMemoryAccountRepository의 실제 로직.
DB 구현체(예: SqlAccountRepository)는 나중에 별도 파일(repository_sql.py)로 추가할 것 —
로직을 InMemoryAccountRepository로 먼저 검증한 뒤 교체.
"""

from typing import Protocol

from .domain import Account,AccountNotFoundError


class AccountRepository(Protocol):
    def find_by_id(self, account_id: str) -> Account: ...
    def find_all(self) -> list[Account]: ...
    def find_by_owner_id(self, owner_id: str) -> list[Account]: ...
    def save(self, account: Account) -> None: ...


class MemoryAccountRepository:
    """AccountRepository를 상속하지 않아도 됨 — 메서드 시그니처만 맞으면 protocol을 만족."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}

    def find_by_id(self, account_id: str) -> Account:
        """없으면 AccountNotFoundError."""
        find_account = self._accounts.get(account_id)
        if find_account is None:
            raise AccountNotFoundError(account_id)
        else:
            return find_account

    def find_all(self) -> list[Account]:
        account_list = []
        for account in self._accounts.values():
            account_list.append(account)
        return account_list

    def find_by_owner_id(self, owner_id: str) -> list[Account]:
        """owner_id가 일치하는 계좌 전부 (없으면 빈 리스트, 예외 아님)."""
        raise NotImplementedError

    def save(self, account: Account) -> None:
        self._accounts[account.account_id] = account

