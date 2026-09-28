"""api/app.py의 REST 엔드포인트(계좌/카드/청구서 조회 + 이체/카드관리/청구서납부 실행)
통합 테스트. api_client 픽스처(conftest.py)가 실제 TestClient로 앱을 띄우므로, 매 테스트가
깨끗한 데모 데이터(demo-acc-1: 생활비 500000 / demo-acc-2: 저축 2000000 / demo-card-1 /
demo-bill-1)로 시작한다.
"""


def test_list_accounts_returns_demo_data(api_client):
    res = api_client.get("/api/accounts")
    assert res.status_code == 200
    accounts = {a["account_id"]: a for a in res.json()}
    assert accounts["demo-acc-1"]["balance"] == 500000
    assert accounts["demo-acc-1"]["nickname"] == "생활비"
    assert accounts["demo-acc-2"]["balance"] == 2000000


def test_list_cards_returns_demo_card(api_client):
    res = api_client.get("/api/cards")
    assert res.status_code == 200
    cards = res.json()
    assert len(cards) == 1
    assert cards[0] == {
        "card_id": "demo-card-1",
        "account_id": "demo-acc-1",
        "name": "생활비 체크카드",
        "kind": "체크",
        "status": "USABLE",
    }


def test_list_bills_returns_unpaid_demo_bill(api_client):
    res = api_client.get("/api/bills")
    assert res.status_code == 200
    bills = res.json()
    assert len(bills) == 1
    assert bills[0]["bill_id"] == "demo-bill-1"
    assert bills[0]["status"] == "UNPAID"


def test_transactions_empty_before_any_activity(api_client):
    res = api_client.get("/api/accounts/demo-acc-1/transactions")
    assert res.status_code == 200
    assert res.json() == []


def test_transactions_for_unknown_account_is_404(api_client):
    res = api_client.get("/api/accounts/no-such-account/transactions")
    assert res.status_code == 404


class TestTransfer:
    def test_success_updates_both_balances_and_records_transactions(self, api_client):
        res = api_client.post(
            "/api/transfer",
            json={"from_id": "demo-acc-1", "to_id": "demo-acc-2", "amount": 10000},
        )
        assert res.status_code == 200
        accounts = {a["account_id"]: a for a in res.json()}
        assert accounts["demo-acc-1"]["balance"] == 490000
        assert accounts["demo-acc-2"]["balance"] == 2010000

        out_tx = api_client.get("/api/accounts/demo-acc-1/transactions").json()
        assert len(out_tx) == 1
        assert out_tx[0]["transaction_type"] == "TRANSFER_OUT"
        assert out_tx[0]["amount"] == 10000
        assert out_tx[0]["counterpart_id"] == "demo-acc-2"

        in_tx = api_client.get("/api/accounts/demo-acc-2/transactions").json()
        assert len(in_tx) == 1
        assert in_tx[0]["transaction_type"] == "TRANSFER_IN"
        assert in_tx[0]["counterpart_id"] == "demo-acc-1"

    def test_self_transfer_is_rejected(self, api_client):
        res = api_client.post(
            "/api/transfer",
            json={"from_id": "demo-acc-1", "to_id": "demo-acc-1", "amount": 1000},
        )
        assert res.status_code == 400
        assert "같은 계좌" in res.json()["detail"]

    def test_insufficient_balance_is_rejected(self, api_client):
        res = api_client.post(
            "/api/transfer",
            json={"from_id": "demo-acc-1", "to_id": "demo-acc-2", "amount": 999_999_999},
        )
        assert res.status_code == 400
        assert "잔액" in res.json()["detail"]

    def test_unknown_to_account_is_rejected(self, api_client):
        # to_id는 propose() 소유권 검증 대상이 아니라 approve()의 실제 실행(transfer()) 중에야
        # AccountNotFoundError가 나므로, approve()의 넓은 except가 이를 ActionResult 실패로
        # 감싼다 — 그래서 (from_id 자체가 없을 때의 404와 달리) 400으로 응답됨.
        res = api_client.post(
            "/api/transfer",
            json={"from_id": "demo-acc-1", "to_id": "no-such-account", "amount": 1000},
        )
        assert res.status_code == 400
        assert "계좌를 찾을 수 없습니다" in res.json()["detail"]

    def test_unknown_from_account_is_404(self, api_client):
        # from_id는 propose()의 verify_owner 단계에서 바로 조회되므로, 여기서 난
        # AccountNotFoundError는 approve()를 거치지 않고 그대로 전파되어 404가 된다.
        res = api_client.post(
            "/api/transfer",
            json={"from_id": "no-such-account", "to_id": "demo-acc-2", "amount": 1000},
        )
        assert res.status_code == 404

    def test_failed_transfer_does_not_change_balance(self, api_client):
        api_client.post(
            "/api/transfer",
            json={"from_id": "demo-acc-1", "to_id": "demo-acc-2", "amount": 999_999_999},
        )
        accounts = {a["account_id"]: a for a in api_client.get("/api/accounts").json()}
        assert accounts["demo-acc-1"]["balance"] == 500000
        assert accounts["demo-acc-2"]["balance"] == 2000000


class TestCardActions:
    def test_lock_then_unlock_round_trip(self, api_client):
        locked = api_client.post("/api/cards/demo-card-1/lock").json()
        assert locked["status"] == "LOCKED"

        unlocked = api_client.post("/api/cards/demo-card-1/unlock").json()
        assert unlocked["status"] == "USABLE"

    def test_locking_an_already_locked_card_is_rejected(self, api_client):
        api_client.post("/api/cards/demo-card-1/lock")
        res = api_client.post("/api/cards/demo-card-1/lock")
        assert res.status_code == 400

    def test_unlocking_a_usable_card_is_rejected(self, api_client):
        res = api_client.post("/api/cards/demo-card-1/unlock")
        assert res.status_code == 400

    def test_report_lost_then_lock_is_rejected(self, api_client):
        lost = api_client.post("/api/cards/demo-card-1/lost").json()
        assert lost["status"] == "LOST"

        res = api_client.post("/api/cards/demo-card-1/lock")
        assert res.status_code == 400

    def test_reissue_requires_lost_status(self, api_client):
        res = api_client.post(
            "/api/cards/demo-card-1/reissue", json={"delivery_address": "HOME"}
        )
        assert res.status_code == 400
        assert "분실 처리된" in res.json()["detail"]

    def test_reissue_after_lost_succeeds_then_rejects_duplicate(self, api_client):
        api_client.post("/api/cards/demo-card-1/lost")

        first = api_client.post(
            "/api/cards/demo-card-1/reissue", json={"delivery_address": "HOME"}
        )
        assert first.status_code == 200
        assert first.json()["delivery_address"] == "HOME"
        assert first.json()["status"] == "RECEIVED"

        second = api_client.post(
            "/api/cards/demo-card-1/reissue", json={"delivery_address": "WORK"}
        )
        assert second.status_code == 400
        assert "이미 진행 중" in second.json()["detail"]

    def test_reissue_with_invalid_delivery_address_is_400(self, api_client):
        api_client.post("/api/cards/demo-card-1/lost")
        res = api_client.post(
            "/api/cards/demo-card-1/reissue", json={"delivery_address": "MARS"}
        )
        assert res.status_code == 400


class TestBillPayment:
    def test_pay_bill_deducts_balance_and_removes_from_unpaid_list(self, api_client):
        res = api_client.post(
            "/api/bills/demo-bill-1/pay", json={"account_id": "demo-acc-1"}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["bill"]["status"] == "PAID"
        assert body["account"]["balance"] == 455000

        assert api_client.get("/api/bills").json() == []

        tx = api_client.get("/api/accounts/demo-acc-1/transactions").json()
        assert len(tx) == 1
        assert tx[0]["transaction_type"] == "BILL_PAYMENT"
        assert tx[0]["amount"] == 45000
        assert tx[0]["bill_id"] == "demo-bill-1"

    def test_paying_an_already_paid_bill_is_rejected(self, api_client):
        api_client.post("/api/bills/demo-bill-1/pay", json={"account_id": "demo-acc-1"})
        res = api_client.post(
            "/api/bills/demo-bill-1/pay", json={"account_id": "demo-acc-1"}
        )
        assert res.status_code == 400
        assert "이미 납부" in res.json()["detail"]

    def test_pay_all_completes_all_unpaid_bills(self, api_client):
        res = api_client.post(
            "/api/bills/pay-all",
            json={"account_id": "demo-acc-1", "bill_ids": ["demo-bill-1"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["attempts"] == [{"bill_id": "demo-bill-1", "outcome": "COMPLETED"}]
        assert body["account"]["balance"] == 455000
        assert api_client.get("/api/bills").json() == []
