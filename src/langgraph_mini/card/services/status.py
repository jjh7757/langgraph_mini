"""카드 상태 변경 서비스 (분실 정지 / 일시 잠금 / 잠금 해제).

세 메서드 모두 상태만 바꿈 — 계좌 잔액이나 거래 내역(Transaction)에는 손대지 않음.
소유권 검증(이 카드가 요청자 소유인지)은 여기서 하지 않음 — Orchestration Service 책임.

"정지 후 재발급"(분실 정지 → 재발급을 이어서 처리) 기능은 이 서비스의 메서드가 아니라
Orchestration Service가 block_as_lost() 승인 → request_reissue() 승인을 각각 따로
거쳐서 순서대로 호출하는 조합임. 재발급이 실패/취소돼도 이미 끝난 분실 정지는
되돌리지 않음 — 두 호출이 서로 독립적이라 별도 롤백 로직이 필요 없음.
"""

from typing import Protocol

from ..domain import Card
from ..repository import CardRepository


class CardStatusService(Protocol):
    def block_as_lost(self, card_id: str) -> Card: ...
    def lock_temporarily(self, card_id: str) -> Card: ...
    def unlock(self, card_id: str) -> Card: ...


class DefaultCardStatusService:
    def __init__(self, card_repo: CardRepository) -> None:
        self._card_repo = card_repo

    def block_as_lost(self, card_id: str) -> Card:
        """find_by_id → card.block_as_lost() → save → 반환. 셋 다 같은 흐름."""
        ...

    def lock_temporarily(self, card_id: str) -> Card:
        ...

    def unlock(self, card_id: str) -> Card:
        ...
