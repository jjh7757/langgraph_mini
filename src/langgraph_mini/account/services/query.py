"""계좌 조회 관련 서비스.

TODO(직접 구현): DefaultAccountQueryService의 실제 로직.
"""

from typing import Protocol

from ..domain import Account, Transaction
from ..repository import AccountRepository


class AccountQueryService(Protocol):
    def get_account(self, account_id: str) -> Account: ...
    def get_total_balance(self, account_ids: list[str]) -> int: ...
    def get_transactions(self, account_id: str) -> list[Transaction]: ...


class DefaultAccountQueryService:
    def __init__(self, repo: AccountRepository) -> None:
        self._repo = repo

    def get_account(self, account_id: str) -> Account:
        return self._repo.find_by_id(account_id)

    def get_total_balance(self, account_ids: list[str]) -> int:
        total = 0
        for account_id in account_ids:
            account = self.get_account(account_id)
            total += account.balance
        return total

    def get_transactions(self, account_id: str) -> list[Transaction]:
        """TODO(결정 필요): Transaction을 어디서 가져올지.
        지금 AccountRepository엔 Transaction 저장/조회 메서드가 없음.
        TransactionRepository를 새로 만들지, AccountRepository에 합칠지 정할 것.
        """
        raise NotImplementedError
