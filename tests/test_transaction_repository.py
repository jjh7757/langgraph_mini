from langgraph_mini.account.domain import Transaction, TransactionType
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository


def test_find_by_account_id_returns_only_that_accounts_transactions():
    repo = MemoryTransactionRepository()
    t1 = Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=100)
    t2 = Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_IN, amount=200)
    t3 = Transaction(account_id="a2", transaction_type=TransactionType.TRANSFER_IN, amount=300)
    repo.save(t1)
    repo.save(t2)
    repo.save(t3)

    assert repo.find_by_account_id("a1") == [t1, t2]


def test_find_by_account_id_returns_empty_list_when_none_match():
    repo = MemoryTransactionRepository()

    assert repo.find_by_account_id("no-such-account") == []


def test_save_appends_rather_than_overwrites():
    repo = MemoryTransactionRepository()
    repo.save(Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=100))
    repo.save(Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=100))

    assert len(repo.find_by_account_id("a1")) == 2
