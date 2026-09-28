"""카드 조회 서비스.

get_cards는 owner_id 기준(그 소유자의 모든 계좌에 연결된 카드 전부)으로 동작함 —
AccountQueryService.get_accounts와 같은 패턴. 카드 하나는 계좌 하나에만 연결되므로
계좌 목록을 먼저 구한 뒤 계좌별 카드를 모아서 합치면 됨.
"""

from typing import Protocol

from ...account.repository import AccountRepository
from ..domain import Card
from ..repository import CardRepository


class CardQueryService(Protocol):
    def get_card(self, card_id: str) -> Card: ...
    def get_cards(self, owner_id: str) -> list[Card]: ...


class DefaultCardQueryService:
    def __init__(self, card_repo: CardRepository, account_repo: AccountRepository) -> None:
        self._card_repo = card_repo
        self._account_repo = account_repo

    def get_card(self, card_id: str) -> Card:
        ...

    def get_cards(self, owner_id: str) -> list[Card]:
        """1) account_repo.find_by_owner_id(owner_id)로 그 소유자의 계좌 목록 조회
        2) 각 계좌마다 card_repo.find_by_account_id(account_id) 호출해서 리스트 합치기
        계좌가 하나도 없으면(따라서 카드도 없으면) 빈 리스트."""
        ...
