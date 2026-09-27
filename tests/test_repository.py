import pytest

from langgraph_mini.account.domain import Account, AccountNotFoundError
from langgraph_mini.account.repository import MemoryAccountRepository


def test_save_then_find_by_id():
    repo = MemoryAccountRepository()
    account = Account(account_id="a1", owner_id="u1", nickname="철수", balance=1000)

    repo.save(account)

    assert repo.find_by_id("a1") == account


def test_find_by_id_raises_when_not_found():
    repo = MemoryAccountRepository()

    with pytest.raises(AccountNotFoundError):
        repo.find_by_id("no-such-id")


def test_find_all_returns_every_saved_account():
    repo = MemoryAccountRepository()
    account1 = Account(account_id="a1", owner_id="u1", nickname="철수", balance=1000)
    account2 = Account(account_id="a2", owner_id="u2", nickname="영희", balance=500)

    repo.save(account1)
    repo.save(account2)

    assert repo.find_all() == [account1, account2]


def test_find_by_owner_id_returns_only_that_owners_accounts():
    repo = MemoryAccountRepository()
    account1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    account2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=500)
    account3 = Account(account_id="a3", owner_id="u2", nickname="travel", balance=200)
    repo.save(account1)
    repo.save(account2)
    repo.save(account3)

    assert repo.find_by_owner_id("u1") == [account1, account2]


def test_find_by_owner_id_returns_empty_list_when_none_match():
    repo = MemoryAccountRepository()

    assert repo.find_by_owner_id("nobody") == []
