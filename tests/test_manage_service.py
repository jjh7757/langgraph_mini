import pytest

from langgraph_mini.account.domain import Account, DuplicateNicknameError
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.services.manage import DefaultAccountManageService


def _service_with(*accounts: Account):
    repo = MemoryAccountRepository()
    for account in accounts:
        repo.save(account)
    return DefaultAccountManageService(repo), repo


def test_rename_account_changes_nickname():
    account = Account(account_id="a1", owner_id="u1", nickname="old", balance=1000)
    service, repo = _service_with(account)

    result = service.rename_account("a1", "  new  ")

    assert result.nickname == "new"
    assert repo.find_by_id("a1").nickname == "new"


def test_rename_account_raises_on_duplicate_within_same_owner():
    account1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    account2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=500)
    service, _ = _service_with(account1, account2)

    with pytest.raises(DuplicateNicknameError):
        service.rename_account("a2", "life")


def test_rename_account_allows_duplicate_across_different_owners():
    account1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    account2 = Account(account_id="a2", owner_id="u2", nickname="save", balance=500)
    service, repo = _service_with(account1, account2)

    service.rename_account("a2", "life")

    assert repo.find_by_id("a2").nickname == "life"


def test_rename_account_allows_renaming_to_its_own_current_nickname():
    account = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    service, repo = _service_with(account)

    service.rename_account("a1", "life")

    assert repo.find_by_id("a1").nickname == "life"
