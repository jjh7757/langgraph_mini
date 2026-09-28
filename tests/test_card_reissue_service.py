import pytest

from langgraph_mini.card.domain import (
    Card,
    CardKind,
    CardNotLostError,
    CardStatus,
    DeliveryAddress,
    ReissueRequestAlreadyExistsError,
    ReissueRequestNotFoundError,
    ReissueRequestNotModifiableError,
    ReissueStatus,
)
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.reissue_request_repository import MemoryReissueRequestRepository
from langgraph_mini.card.services.reissue import DefaultCardReissueService


def _service_with(*cards: Card):
    card_repo = MemoryCardRepository()
    for card in cards:
        card_repo.save(card)
    reissue_repo = MemoryReissueRequestRepository()
    return DefaultCardReissueService(card_repo, reissue_repo), card_repo, reissue_repo


def _lost_card() -> Card:
    return Card(
        card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK, status=CardStatus.LOST
    )


def test_request_reissue_creates_request_for_lost_card():
    service, _, reissue_repo = _service_with(_lost_card())

    result = service.request_reissue("c1", DeliveryAddress.HOME, "r1")

    assert result.card_id == "c1"
    assert result.delivery_address is DeliveryAddress.HOME
    assert result.status is ReissueStatus.RECEIVED
    assert reissue_repo.find_by_id("r1") == result


def test_request_reissue_raises_when_card_not_lost():
    card = Card(
        card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK, status=CardStatus.USABLE
    )
    service, _, _ = _service_with(card)

    with pytest.raises(CardNotLostError):
        service.request_reissue("c1", DeliveryAddress.HOME, "r1")


def test_request_reissue_raises_when_existing_non_cancelled_request():
    service, _, _ = _service_with(_lost_card())
    service.request_reissue("c1", DeliveryAddress.HOME, "r1")

    with pytest.raises(ReissueRequestAlreadyExistsError):
        service.request_reissue("c1", DeliveryAddress.WORK, "r2")


def test_request_reissue_allowed_when_existing_request_cancelled():
    service, _, reissue_repo = _service_with(_lost_card())
    service.request_reissue("c1", DeliveryAddress.HOME, "r1")
    service.cancel_reissue_request("r1")

    result = service.request_reissue("c1", DeliveryAddress.WORK, "r2")

    assert result.request_id == "r2"
    assert reissue_repo.find_by_id("r2") == result


def test_request_reissue_does_not_change_card_status():
    service, card_repo, _ = _service_with(_lost_card())

    service.request_reissue("c1", DeliveryAddress.HOME, "r1")

    assert card_repo.find_by_id("c1").status is CardStatus.LOST


def test_get_reissue_request_raises_when_not_found():
    service, _, _ = _service_with(_lost_card())

    with pytest.raises(ReissueRequestNotFoundError):
        service.get_reissue_request("no-such-request")


def test_get_reissue_requests_by_card_returns_empty_list_when_none():
    service, _, _ = _service_with(_lost_card())

    assert service.get_reissue_requests_by_card("c1") == []


def test_change_delivery_address_updates_and_persists():
    service, _, reissue_repo = _service_with(_lost_card())
    service.request_reissue("c1", DeliveryAddress.HOME, "r1")

    result = service.change_delivery_address("r1", DeliveryAddress.WORK)

    assert result.delivery_address is DeliveryAddress.WORK
    assert reissue_repo.find_by_id("r1").delivery_address is DeliveryAddress.WORK


def test_cancel_reissue_request_updates_and_persists():
    service, _, reissue_repo = _service_with(_lost_card())
    service.request_reissue("c1", DeliveryAddress.HOME, "r1")

    result = service.cancel_reissue_request("r1")

    assert result.status is ReissueStatus.CANCELLED
    assert reissue_repo.find_by_id("r1").status is ReissueStatus.CANCELLED


def test_cancel_reissue_request_raises_when_not_modifiable():
    service, _, reissue_repo = _service_with(_lost_card())
    service.request_reissue("c1", DeliveryAddress.HOME, "r1")
    service.cancel_reissue_request("r1")

    with pytest.raises(ReissueRequestNotModifiableError):
        service.cancel_reissue_request("r1")
