"""계좌 관리(별명 변경 등) 서비스.

TODO(직접 구현): DefaultAccountManageService의 실제 로직.
"""

from typing import Protocol

from ..domain import Account
from ..repository import AccountRepository


class AccountManageService(Protocol):
    def rename_account(self, account_id: str, new_alias: str) -> Account: ...


class DefaultAccountManageService:
    def __init__(self, repo: AccountRepository) -> None:
        self._repo = repo

    def rename_account(self, account_id: str, new_alias: str) -> Account:
        raise NotImplementedError
