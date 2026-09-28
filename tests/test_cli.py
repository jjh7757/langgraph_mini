from langgraph_mini.account.repository_json import JsonAccountRepository
from langgraph_mini.billing.repository_json import JsonBillRepository
from langgraph_mini.card.repository_json import JsonCardRepository
from langgraph_mini.cli import DEMO_OWNER_ID, _ensure_demo_data


def test_ensure_demo_data_seeds_accounts_cards_bills(tmp_path):
    _ensure_demo_data(str(tmp_path))

    accounts = JsonAccountRepository(tmp_path / "accounts.json").find_by_owner_id(DEMO_OWNER_ID)
    cards = JsonCardRepository(tmp_path / "cards.json").find_by_account_id("demo-acc-1")
    bills = JsonBillRepository(tmp_path / "bills.json").find_by_owner_id(DEMO_OWNER_ID)

    assert {a.nickname for a in accounts} == {"생활비", "저축"}
    assert len(cards) == 1
    assert len(bills) == 1


def test_ensure_demo_data_is_idempotent(tmp_path):
    _ensure_demo_data(str(tmp_path))
    _ensure_demo_data(str(tmp_path))  # 두 번째 호출은 아무것도 추가하면 안 됨

    accounts = JsonAccountRepository(tmp_path / "accounts.json").find_by_owner_id(DEMO_OWNER_ID)
    assert len(accounts) == 2
