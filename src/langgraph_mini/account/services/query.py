"""계좌 조회 관련 서비스.

TODO(직접 구현): 아래 NotImplementedError 메서드들의 실제 로직.

get_total_balance/get_accounts는 owner_id 기준(그 소유자의 모든 계좌)으로 동작함 —
호출하는 쪽이 계좌 id 목록을 미리 알 필요가 없음.

get_transactions는 필터링·정렬(최근순)을 여기서 수행 (Repository는 순수 저장/조회만).
카드결제 내역은 TransactionView.card에 카드 정보까지 채워서 반환.
"""

from dataclasses import dataclass
from typing import Protocol

from ..card_repository import CardRepository
from ..domain import Account, Card, Transaction, TransactionFilter
from ..repository import AccountRepository
from ..transaction_repository import TransactionRepository


@dataclass
class TransactionView:
    """거래 내역 조회 결과 한 줄. 카드결제가 아니면 card는 None."""

    transaction: Transaction
    card: Card | None = None


class AccountQueryService(Protocol):
    def get_account(self, account_id: str) -> Account: ...
    def get_accounts(self, owner_id: str) -> list[Account]: ...
    def get_total_balance(self, owner_id: str) -> int: ...
    def get_transactions(
        self, account_id: str, filter: TransactionFilter | None = None
    ) -> list[TransactionView]: ...


class DefaultAccountQueryService:
    def __init__(
        self,
        account_repo: AccountRepository,
        transaction_repo: TransactionRepository,
        card_repo: CardRepository,
    ) -> None:
        self._account_repo = account_repo
        self._transaction_repo = transaction_repo
        self._card_repo = card_repo

    def get_account(self, account_id: str) -> Account:
        return self._account_repo.find_by_id(account_id)

    def get_accounts(self, owner_id: str) -> list[Account]:
        return self._account_repo.find_by_owner_id(owner_id)

    def get_total_balance(self, owner_id: str) -> int:
        """owner_id의 모든 계좌 balance 합산. 계좌가 하나도 없으면 0."""
        raise NotImplementedError

    def get_transactions(
        self, account_id: str, filter: TransactionFilter | None = None
    ) -> list[TransactionView]:
        """순서:
        1) self._transaction_repo.find_by_account_id(account_id)로 전체 조회
        2) filter가 있으면 start_date/end_date(포함)·min_amount/max_amount·
           transaction_type 조건으로 걸러내기 (None인 조건은 건너뜀)
        3) created_at 기준 최근순(내림차순) 정렬
        4) transaction_type이 CARD_PAYMENT인 항목만 card_id로 self._card_repo.find_by_id
           호출해서 TransactionView.card 채우기, 나머지는 card=None
        """
        raise NotImplementedError
