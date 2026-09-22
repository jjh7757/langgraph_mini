import pytest

from langgraph_mini.account.domain import Account, AccountNotFoundError
from langgraph_mini.account.repository import MemoryAccountRepository


def test_save_then_find_by_id():
    repo = MemoryAccountRepository()
    account = Account(id="a1", alias="철수", balance=1000)

    repo.save(account)

    assert repo.find_by_id("a1") == account


def test_find_by_id_raises_when_not_found():
    repo = MemoryAccountRepository()

    with pytest.raises(AccountNotFoundError):
        repo.find_by_id("no-such-id")


def test_find_all_returns_every_saved_account():
    repo = MemoryAccountRepository()
    account1 = Account(id="a1", alias="철수", balance=1000)
    account2 = Account(id="a2", alias="영희", balance=500)

    repo.save(account1)
    repo.save(account2)

    assert repo.find_all() == [account1, account2]
