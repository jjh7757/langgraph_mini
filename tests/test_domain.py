import pytest

from langgraph_mini.account.domain import Account, InsufficientBalanceError


def _account(balance: int = 1000) -> Account:
    return Account(account_id="a1", owner_id="u1", nickname="test", balance=balance)


def test_withdraw_reduces_balance():
    account = _account(1000)
    account.withdraw(300)
    assert account.balance == 700


def test_withdraw_raises_when_insufficient_balance():
    account = _account(100)
    with pytest.raises(InsufficientBalanceError):
        account.withdraw(200)
    assert account.balance == 100  # 실패 시 잔액 그대로


def test_withdraw_raises_when_amount_not_positive():
    account = _account(1000)
    with pytest.raises(ValueError):
        account.withdraw(0)
    with pytest.raises(ValueError):
        account.withdraw(-10)


def test_deposit_increases_balance():
    account = _account(1000)
    account.deposit(500)
    assert account.balance == 1500


def test_deposit_raises_when_amount_not_positive():
    account = _account(1000)
    with pytest.raises(ValueError):
        account.deposit(0)
    with pytest.raises(ValueError):
        account.deposit(-10)


def test_rename_changes_nickname():
    account = _account()
    account.rename("  새 별명  ")
    assert account.nickname == "새 별명"  # 앞뒤 공백 제거


def test_rename_raises_when_empty():
    account = _account()
    with pytest.raises(ValueError):
        account.rename("   ")


def test_rename_raises_when_too_long():
    account = _account()
    with pytest.raises(ValueError):
        account.rename("a" * 21)
