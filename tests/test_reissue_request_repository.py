import pytest

from langgraph_mini.card.domain import DeliveryAddress, ReissueRequest, ReissueRequestNotFoundError
from langgraph_mini.card.reissue_request_repository import MemoryReissueRequestRepository


def test_save_then_find_by_id():
    repo = MemoryReissueRequestRepository()
    request = ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)

    repo.save(request)

    assert repo.find_by_id("r1") == request


def test_find_by_id_raises_when_not_found():
    repo = MemoryReissueRequestRepository()

    with pytest.raises(ReissueRequestNotFoundError):
        repo.find_by_id("no-such-request")


def test_find_by_card_id_returns_only_that_cards_requests():
    repo = MemoryReissueRequestRepository()
    request1 = ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)
    request2 = ReissueRequest(request_id="r2", card_id="c1", delivery_address=DeliveryAddress.WORK)
    request3 = ReissueRequest(request_id="r3", card_id="c2", delivery_address=DeliveryAddress.HOME)
    repo.save(request1)
    repo.save(request2)
    repo.save(request3)

    assert repo.find_by_card_id("c1") == [request1, request2]


def test_find_by_card_id_returns_empty_list_when_none():
    repo = MemoryReissueRequestRepository()

    assert repo.find_by_card_id("no-such-card") == []
