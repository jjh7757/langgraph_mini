"""계좌 관리(별명 변경 등) 서비스."""

from typing import Protocol

from ..domain import Account, DuplicateNicknameError
from ..repository import AccountRepository


class AccountManageService(Protocol):
    def rename_account(self, account_id: str, new_nickname: str) -> Account: ...


class DefaultAccountManageService:
    def __init__(self, repo: AccountRepository) -> None:
        self._repo = repo

    def rename_account(self, account_id: str, new_nickname: str) -> Account:
        account = self._repo.find_by_id(account_id)

        stripped = new_nickname.strip()
        siblings = self._repo.find_by_owner_id(account.owner_id)
        if any(
            sibling.account_id != account.account_id and sibling.nickname == stripped
            for sibling in siblings
        ):
            raise DuplicateNicknameError(stripped)

        account.rename(new_nickname)
        self._repo.save(account)
        return account
