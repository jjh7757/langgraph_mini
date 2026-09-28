"""카드 재발급 신청 서비스 (신청 / 조회 / 배송지 변경·취소).

request_id는 호출하는 쪽(Orchestration)이 생성해서 넘김 — account_id/card_id와
같은 패턴(이 서비스는 id를 스스로 생성하지 않음).

"조회할 신청이 불명확하면 목록에서 선택받고" / "해당 신청이 없으면 기록이 없음을
안내" 부분은 여기서 처리하지 않음 — get_reissue_requests_by_card가 반환한
목록(없으면 빈 리스트)을 가지고 Orchestration이 되묻거나 안내함.
"""

from typing import Protocol

from ..domain import (
    CardNotLostError,
    CardStatus,
    DeliveryAddress,
    ReissueRequest,
    ReissueRequestAlreadyExistsError,
    ReissueStatus,
)
from ..repository import CardRepository
from ..reissue_request_repository import ReissueRequestRepository


class CardReissueService(Protocol):
    def request_reissue(
        self, card_id: str, delivery_address: DeliveryAddress, request_id: str
    ) -> ReissueRequest: ...

    def get_reissue_request(self, request_id: str) -> ReissueRequest: ...

    def get_reissue_requests_by_card(self, card_id: str) -> list[ReissueRequest]: ...

    def change_delivery_address(
        self, request_id: str, new_address: DeliveryAddress
    ) -> ReissueRequest: ...

    def cancel_reissue_request(self, request_id: str) -> ReissueRequest: ...


class DefaultCardReissueService:
    def __init__(
        self, card_repo: CardRepository, reissue_repo: ReissueRequestRepository
    ) -> None:
        self._card_repo = card_repo
        self._reissue_repo = reissue_repo

    def request_reissue(
        self, card_id: str, delivery_address: DeliveryAddress, request_id: str
    ) -> ReissueRequest:
        """순서:
        1) card_repo.find_by_id(card_id)로 카드 확인 → status가 LOST가 아니면 CardNotLostError
        2) reissue_repo.find_by_card_id(card_id) 중 status != CANCELLED인 게 있으면
           ReissueRequestAlreadyExistsError(그 기존 신청을 args에 담아서) —
           호출한 쪽이 "이미 신청이 있다"고 안내할 수 있게
        3) 새 ReissueRequest(request_id, card_id, delivery_address) 생성 후 save, 반환
        카드 자체의 status는 여기서 바꾸지 않음(LOST 그대로 유지)."""
        card = self._card_repo.find_by_id(card_id)
        if card.status is not CardStatus.LOST:
            raise CardNotLostError(card_id)

        existing = [
            request
            for request in self._reissue_repo.find_by_card_id(card_id)
            if request.status is not ReissueStatus.CANCELLED
        ]
        if existing:
            raise ReissueRequestAlreadyExistsError(existing[0])

        request = ReissueRequest(
            request_id=request_id, card_id=card_id, delivery_address=delivery_address
        )
        self._reissue_repo.save(request)
        return request

    def get_reissue_request(self, request_id: str) -> ReissueRequest:
        """reissue_repo.find_by_id 그대로 위임. 없으면 ReissueRequestNotFoundError."""
        return self._reissue_repo.find_by_id(request_id)

    def get_reissue_requests_by_card(self, card_id: str) -> list[ReissueRequest]:
        """reissue_repo.find_by_card_id 그대로 위임. 없으면 빈 리스트."""
        return self._reissue_repo.find_by_card_id(card_id)

    def change_delivery_address(
        self, request_id: str, new_address: DeliveryAddress
    ) -> ReissueRequest:
        """find_by_id → request.change_delivery_address(new_address) → save → 반환.
        RECEIVED 상태가 아니면 ReissueRequestNotModifiableError(도메인 메서드가 발생시킴)."""
        request = self._reissue_repo.find_by_id(request_id)
        request.change_delivery_address(new_address)
        self._reissue_repo.save(request)
        return request

    def cancel_reissue_request(self, request_id: str) -> ReissueRequest:
        """find_by_id → request.cancel() → save → 반환."""
        request = self._reissue_repo.find_by_id(request_id)
        request.cancel()
        self._reissue_repo.save(request)
        return request
