import pytest

from langgraph_mini.card.domain import (
    Card,
    CardAlreadyLostError,
    CardKind,
    CardNotLockedError,
    CardNotUsableError,
    CardStatus,
    DeliveryAddress,
    ReissueRequest,
    ReissueRequestNotModifiableError,
    ReissueStatus,
)


def _card(status: CardStatus = CardStatus.USABLE) -> Card:
    return Card(
        card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK, status=status
    )


def test_block_as_lost_from_usable():
    card = _card(CardStatus.USABLE)
    card.block_as_lost()
    assert card.status is CardStatus.LOST


def test_block_as_lost_from_locked():
    card = _card(CardStatus.LOCKED)
    card.block_as_lost()
    assert card.status is CardStatus.LOST


def test_block_as_lost_raises_when_already_lost():
    card = _card(CardStatus.LOST)
    with pytest.raises(CardAlreadyLostError):
        card.block_as_lost()


def test_lock_temporarily_from_usable():
    card = _card(CardStatus.USABLE)
    card.lock_temporarily()
    assert card.status is CardStatus.LOCKED


def test_lock_temporarily_raises_when_already_locked():
    card = _card(CardStatus.LOCKED)
    with pytest.raises(CardNotUsableError):
        card.lock_temporarily()


def test_lock_temporarily_raises_when_lost():
    card = _card(CardStatus.LOST)
    with pytest.raises(CardNotUsableError):
        card.lock_temporarily()


def test_unlock_from_locked():
    card = _card(CardStatus.LOCKED)
    card.unlock()
    assert card.status is CardStatus.USABLE


def test_unlock_raises_when_usable():
    card = _card(CardStatus.USABLE)
    with pytest.raises(CardNotLockedError):
        card.unlock()


def test_unlock_raises_when_lost():
    card = _card(CardStatus.LOST)
    with pytest.raises(CardNotLockedError):
        card.unlock()


def _reissue_request(status: ReissueStatus = ReissueStatus.RECEIVED) -> ReissueRequest:
    return ReissueRequest(
        request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME, status=status
    )


def test_change_delivery_address_when_received():
    request = _reissue_request(ReissueStatus.RECEIVED)
    request.change_delivery_address(DeliveryAddress.WORK)
    assert request.delivery_address is DeliveryAddress.WORK


def test_change_delivery_address_raises_when_in_production():
    request = _reissue_request(ReissueStatus.IN_PRODUCTION)
    with pytest.raises(ReissueRequestNotModifiableError):
        request.change_delivery_address(DeliveryAddress.WORK)


def test_cancel_when_received():
    request = _reissue_request(ReissueStatus.RECEIVED)
    request.cancel()
    assert request.status is ReissueStatus.CANCELLED


def test_cancel_raises_when_already_cancelled():
    request = _reissue_request(ReissueStatus.CANCELLED)
    with pytest.raises(ReissueRequestNotModifiableError):
        request.cancel()
