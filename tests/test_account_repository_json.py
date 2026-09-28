import pytest

from langgraph_mini.account.domain import Account, AccountNotFoundError
from langgraph_mini.account.repository_json import JsonAccountRepository


def test_save_then_find_by_id(tmp_path):
    repo = JsonAccountRepository(tmp_path / "accounts.json")
    account = Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000)

    repo.save(account)

    assert repo.find_by_id("a1") == account


def test_find_by_id_raises_when_not_found(tmp_path):
    repo = JsonAccountRepository(tmp_path / "accounts.json")

    with pytest.raises(AccountNotFoundError):
        repo.find_by_id("no-such-account")


def test_find_by_owner_id_returns_only_that_owners_accounts(tmp_path):
    repo = JsonAccountRepository(tmp_path / "accounts.json")
    account1 = Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000)
    account2 = Account(account_id="a2", owner_id="u1", nickname="비상금", balance=2000)
    account3 = Account(account_id="a3", owner_id="u2", nickname="딴사람", balance=3000)
    repo.save(account1)
    repo.save(account2)
    repo.save(account3)

    assert repo.find_by_owner_id("u1") == [account1, account2]


def test_data_survives_reopening_the_repository(tmp_path):
    """재시작 시뮬레이션 — 같은 파일을 새 인스턴스로 열어도 저장된 데이터가 그대로 있어야 함."""
    path = tmp_path / "accounts.json"
    repo = JsonAccountRepository(path)
    repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=70000))

    reopened = JsonAccountRepository(path)

    account = reopened.find_by_id("a1")
    assert account.balance == 70000
    assert account.nickname == "생활비"
