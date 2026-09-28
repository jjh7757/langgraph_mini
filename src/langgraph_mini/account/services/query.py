"""계좌 조회 관련 서비스.

get_total_balance/get_accounts는 owner_id 기준(그 소유자의 모든 계좌)으로 동작함 —
호출하는 쪽이 계좌 id 목록을 미리 알 필요가 없음.

get_transactions는 필터링·정렬(최근순)을 여기서 수행 (Repository는 순수 저장/조회만).
카드결제 내역은 TransactionView.card에 카드 정보까지 채워서 반환.
"""

from dataclasses import dataclass
from typing import Protocol

from ...card.domain import Card
from ...card.repository import CardRepository
from ..domain import Account, Transaction, TransactionFilter, TransactionType
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
    def list_recipients(self, exclude_owner_id: str) -> list[Account]: ...


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
        return sum(account.balance for account in self.get_accounts(owner_id))

    def list_recipients(self, exclude_owner_id: str) -> list[Account]:
        """이체 받는사람 후보 — exclude_owner_id(요청자 본인) 소유가 아닌 계좌 전부.
        타인 계좌라 balance까지 그대로 노출하면 안 됨(어디까지 보여줄지는 API 응답
        직렬화 계층의 책임 — 여기서는 "본인 것만 뺀 계좌 목록"이라는 조회 자체만 담당)."""
        return [
            account
            for account in self._account_repo.find_all()
            if account.owner_id != exclude_owner_id
        ]

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
        transactions = self._transaction_repo.find_by_account_id(account_id)

        if filter is not None:
            transactions = [t for t in transactions if self._matches(t, filter)]

        transactions.sort(key=lambda t: t.created_at, reverse=True)

        views: list[TransactionView] = []
        for transaction in transactions:
            card = None
            if transaction.transaction_type is TransactionType.CARD_PAYMENT and transaction.card_id is not None:
                card = self._card_repo.find_by_id(transaction.card_id)
            views.append(TransactionView(transaction=transaction, card=card))
        return views

    @staticmethod
    def _matches(transaction: Transaction, filter: TransactionFilter) -> bool:
        transaction_date = transaction.created_at.date()
        if filter.start_date is not None and transaction_date < filter.start_date:
            return False
        if filter.end_date is not None and transaction_date > filter.end_date:
            return False
        if filter.min_amount is not None and transaction.amount < filter.min_amount:
            return False
        if filter.max_amount is not None and transaction.amount > filter.max_amount:
            return False
        if (
            filter.transaction_type is not None
            and transaction.transaction_type is not filter.transaction_type
        ):
            return False
        return True
