import pytest

from langgraph_mini.account.domain import (
    Account,
    InsufficientBalanceError,
    TransactionType,
    TransferCondition,
)
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.services.transfer import (
    AccountSelfTransferError,
    ConditionalTransferNotNeededError,
    DefaultAccountTransferService,
    StaleConditionalTransferError,
)
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository


def _service_with(*accounts: Account):
    account_repo = MemoryAccountRepository()
    for account in accounts:
        account_repo.save(account)
    tx_repo = MemoryTransactionRepository()
    return DefaultAccountTransferService(account_repo, tx_repo), account_repo, tx_repo


def test_transfer_moves_balance_between_accounts():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=500)
    service, repo, _ = _service_with(a1, a2)

    service.transfer("a1", "a2", 300)

    assert repo.find_by_id("a1").balance == 700
    assert repo.find_by_id("a2").balance == 800


def test_transfer_records_out_and_in_transactions():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=500)
    service, _, tx_repo = _service_with(a1, a2)

    transactions = service.transfer("a1", "a2", 300)

    assert len(transactions) == 2
    assert {t.transaction_type for t in transactions} == {
        TransactionType.TRANSFER_OUT,
        TransactionType.TRANSFER_IN,
    }
    assert len(tx_repo.find_by_account_id("a1")) == 1
    assert len(tx_repo.find_by_account_id("a2")) == 1


def test_transfer_raises_when_insufficient_balance():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=100)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=500)
    service, repo, _ = _service_with(a1, a2)

    with pytest.raises(InsufficientBalanceError):
        service.transfer("a1", "a2", 999)

    # 실패 시 양쪽 다 잔액 그대로
    assert repo.find_by_id("a1").balance == 100
    assert repo.find_by_id("a2").balance == 500


def test_transfer_raises_on_self_transfer():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    service, _, _ = _service_with(a1)

    with pytest.raises(AccountSelfTransferError):
        service.transfer("a1", "a1", 100)


def test_calculate_conditional_transfer_returns_expected_amount():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    service, _, _ = _service_with(a1)

    quote = service.calculate_conditional_transfer(
        "a1", "a2", TransferCondition(remaining_balance=400)
    )

    assert quote.amount == 600
    assert quote.balance_snapshot == 1000


def test_calculate_conditional_transfer_raises_when_not_needed():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    service, _, _ = _service_with(a1)

    with pytest.raises(ConditionalTransferNotNeededError):
        service.calculate_conditional_transfer(
            "a1", "a2", TransferCondition(remaining_balance=2000)
        )


def test_confirm_conditional_transfer_executes_when_balance_unchanged():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=0)
    service, repo, _ = _service_with(a1, a2)

    quote = service.calculate_conditional_transfer(
        "a1", "a2", TransferCondition(remaining_balance=400)
    )
    service.confirm_conditional_transfer(quote)

    assert repo.find_by_id("a1").balance == 400
    assert repo.find_by_id("a2").balance == 600


def test_confirm_conditional_transfer_raises_when_balance_changed():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=0)
    service, repo, _ = _service_with(a1, a2)

    quote = service.calculate_conditional_transfer(
        "a1", "a2", TransferCondition(remaining_balance=400)
    )
    # 계산 이후 잔액이 바뀜 (다른 요청이 끼어든 상황을 흉내)
    changed = repo.find_by_id("a1")
    changed.deposit(50)
    repo.save(changed)

    with pytest.raises(StaleConditionalTransferError):
        service.confirm_conditional_transfer(quote)


def test_transfer_split_moves_total_and_creates_paired_transactions():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=0)
    a3 = Account(account_id="a3", owner_id="u1", nickname="travel", balance=0)
    service, repo, tx_repo = _service_with(a1, a2, a3)

    transactions = service.transfer_split("a1", [("a2", 200), ("a3", 100)])

    assert repo.find_by_id("a1").balance == 700
    assert repo.find_by_id("a2").balance == 200
    assert repo.find_by_id("a3").balance == 100
    assert len(transactions) == 4  # target마다 OUT/IN 한 쌍씩
    assert len(tx_repo.find_by_account_id("a1")) == 2


def test_transfer_split_raises_when_any_amount_not_positive():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=0)
    service, repo, _ = _service_with(a1, a2)

    with pytest.raises(ValueError):
        service.transfer_split("a1", [("a2", 0)])

    # 검증 실패 시 잔액 변화 없음
    assert repo.find_by_id("a1").balance == 1000


def test_transfer_split_raises_when_total_exceeds_balance():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=100)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=0)
    a3 = Account(account_id="a3", owner_id="u1", nickname="travel", balance=0)
    service, repo, _ = _service_with(a1, a2, a3)

    with pytest.raises(InsufficientBalanceError):
        service.transfer_split("a1", [("a2", 60), ("a3", 60)])

    # 잔액 부족으로 실패하면 어떤 계좌도 안 바뀌어야 함
    assert repo.find_by_id("a1").balance == 100
    assert repo.find_by_id("a2").balance == 0
    assert repo.find_by_id("a3").balance == 0


def test_transfer_split_raises_when_target_includes_self():
    a1 = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    a2 = Account(account_id="a2", owner_id="u1", nickname="save", balance=0)
    service, repo, _ = _service_with(a1, a2)

    with pytest.raises(AccountSelfTransferError):
        service.transfer_split("a1", [("a2", 100), ("a1", 50)])

    # 검증 실패 시 어떤 계좌도 안 바뀌어야 함
    assert repo.find_by_id("a1").balance == 1000
    assert repo.find_by_id("a2").balance == 0
