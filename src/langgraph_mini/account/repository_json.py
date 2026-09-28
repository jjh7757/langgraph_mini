"""AccountRepository의 JSON 파일 구현체.

생성자에서 파일 전체를 읽어 메모리에 올려두고, save()마다 전체를 다시 씀
(json_file_store.JsonFileStore 참고 — 트랜잭션/락 없음, Memory 구현체와 동일한
수준의 동시성 한계를 그대로 인정).
"""

from pathlib import Path

from ..json_file_store import JsonFileStore
from .domain import Account, AccountNotFoundError


class JsonAccountRepository:
    def __init__(self, path: str | Path = "data/accounts.json") -> None:
        self._store = JsonFileStore(path)
        self._accounts: dict[str, Account] = self._store.load()

    def find_by_id(self, account_id: str) -> Account:
        account = self._accounts.get(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)
        return account

    def find_all(self) -> list[Account]:
        return list(self._accounts.values())

    def find_by_owner_id(self, owner_id: str) -> list[Account]:
        return [account for account in self._accounts.values() if account.owner_id == owner_id]

    def save(self, account: Account) -> None:
        self._accounts[account.account_id] = account
        self._store.save_all(self._accounts)
