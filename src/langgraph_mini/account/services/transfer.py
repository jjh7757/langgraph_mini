"""계좌 이체 관련 서비스 (즉시/조건부/분할).

TODO(직접 구현): DefaultAccountTransferService의 실제 로직.
TODO(결정 필요, 코딩 전에): 설계초안/구현_가이드라인.md 5절
    - transfer_conditional의 "조건"이 뭔지 (domain.TransferCondition 채우기)
    - transfer_split에서 일부만 실패하면 전체 롤백인지 best-effort인지
    - 출금/입금 사이 원자성을 어디서 보장할지 (Account, Repository, 혹은 서비스 레벨)
"""

from typing import Protocol

from ..domain import Transaction, TransferCondition
from ..repository import AccountRepository


class AccountTransferService(Protocol):
    def transfer(self, from_id: str, to_id: str, amount: int) -> Transaction: ...

    def transfer_conditional(
        self, from_id: str, to_id: str, amount: int, condition: TransferCondition
    ) -> Transaction: ...

    def transfer_split(
        self, from_id: str, targets: list[tuple[str, int]]
    ) -> list[Transaction]: ...


class DefaultAccountTransferService:
    def __init__(self, repo: AccountRepository) -> None:
        self._repo = repo

    def transfer(self, from_id: str, to_id: str, amount: int) -> Transaction:
        raise NotImplementedError

    def transfer_conditional(
        self, from_id: str, to_id: str, amount: int, condition: TransferCondition
    ) -> Transaction:
        raise NotImplementedError

    def transfer_split(
        self, from_id: str, targets: list[tuple[str, int]]
    ) -> list[Transaction]:
        raise NotImplementedError
