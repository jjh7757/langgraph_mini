"""계좌 관리(별명 변경 등) 서비스.

TODO(직접 구현): rename_account에 "같은 소유자 내 별명 중복 금지" 검증 추가.
"""

from typing import Protocol

from ..domain import Account, DuplicateNicknameError
from ..repository import AccountRepository


class AccountManageService(Protocol):
    def rename_account(self, account_id: str, new_nickname: str) -> Account: ...


class DefaultAccountManageService:
    def __init__(self, repo: AccountRepository) -> None:
        self._repo = repo

    def rename_account(self, account_id: str, new_nickname: str) -> Account:
        """TODO(직접 구현): account.rename() 호출 전에 중복 검사를 추가할 것.

        순서가 중요함 — rename()을 먼저 부르면 검증 실패 시에도 account 객체가
        이미 바뀐 채로 남을 수 있으므로, 중복 검사가 먼저:
        1) account = self._repo.find_by_id(account_id)
        2) stripped = new_nickname.strip()
        3) self._repo.find_by_owner_id(account.owner_id)로 같은 소유자의 다른 계좌들을 가져와서
           (자기 자신 account_id는 제외) nickname이 stripped와 같은 게 있으면
           DuplicateNicknameError
        4) 통과했으면 account.rename(new_nickname) (길이/공백 검증은 여기서 처리됨)
        5) self._repo.save(account)
        6) return account
        """
        account = self._repo.find_by_id(account_id)
        account.rename(new_nickname)
        self._repo.save(account)
        return account
