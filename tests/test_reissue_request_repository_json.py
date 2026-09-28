import pytest

from langgraph_mini.card.domain import (
    DeliveryAddress,
    ReissueRequest,
    ReissueRequestNotFoundError,
    ReissueStatus,
)
from langgraph_mini.card.reissue_request_repository_json import JsonReissueRequestRepository


def test_save_then_find_by_id(tmp_path):
    repo = JsonReissueRequestRepository(tmp_path / "reissue_requests.json")
    request = ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)

    repo.save(request)

    assert repo.find_by_id("r1") == request


def test_find_by_id_raises_when_not_found(tmp_path):
    repo = JsonReissueRequestRepository(tmp_path / "reissue_requests.json")

    with pytest.raises(ReissueRequestNotFoundError):
        repo.find_by_id("no-such-request")


def test_find_by_card_id_returns_only_that_cards_requests(tmp_path):
    repo = JsonReissueRequestRepository(tmp_path / "reissue_requests.json")
    request1 = ReissueRequest(request_id="r1", card_id="c1", delivery_address=DeliveryAddress.HOME)
    request2 = ReissueRequest(request_id="r2", card_id="c2", delivery_address=DeliveryAddress.WORK)
    repo.save(request1)
    repo.save(request2)

    assert repo.find_by_card_id("c1") == [request1]


def test_data_survives_reopening_the_repository(tmp_path):
    path = tmp_path / "reissue_requests.json"
    repo = JsonReissueRequestRepository(path)
    repo.save(
        ReissueRequest(
            request_id="r1",
            card_id="c1",
            delivery_address=DeliveryAddress.WORK,
            status=ReissueStatus.CANCELLED,
        )
    )

    reopened = JsonReissueRequestRepository(path)

    request = reopened.find_by_id("r1")
    assert request.status is ReissueStatus.CANCELLED
    assert request.delivery_address is DeliveryAddress.WORK
