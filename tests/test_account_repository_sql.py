import pytest

from langgraph_mini.account.domain import Account, AccountNotFoundError, Transaction, TransactionType
from langgraph_mini.account.repository_sql import SqlAccountRepository
from langgraph_mini.account.transaction_repository_sql import SqlTransactionRepository


def test_save_then_find_by_id(pg_conn):
    repo = SqlAccountRepository()
    account = Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000)

    repo.save(account)

    assert repo.find_by_id("a1") == account


def test_save_upserts_existing_row(pg_conn):
    repo = SqlAccountRepository()
    repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))

    repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=700))

    assert repo.find_by_id("a1").balance == 700


def test_find_by_id_raises_when_not_found(pg_conn):
    repo = SqlAccountRepository()

    with pytest.raises(AccountNotFoundError):
        repo.find_by_id("no-such-account")


def test_find_by_owner_id_returns_only_that_owners_accounts(pg_conn):
    repo = SqlAccountRepository()
    account1 = Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000)
    account2 = Account(account_id="a2", owner_id="u1", nickname="비상금", balance=2000)
    account3 = Account(account_id="a3", owner_id="u2", nickname="딴사람", balance=3000)
    repo.save(account1)
    repo.save(account2)
    repo.save(account3)

    assert repo.find_by_owner_id("u1") == [account1, account2]


def test_transaction_repository_is_append_only_and_filters_by_account(pg_conn):
    account_repo = SqlAccountRepository()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))
    account_repo.save(Account(account_id="a2", owner_id="u1", nickname="저축", balance=2000))

    tx_repo = SqlTransactionRepository()
    tx_repo.save(
        Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=500)
    )
    tx_repo.save(
        Transaction(account_id="a2", transaction_type=TransactionType.TRANSFER_IN, amount=500)
    )

    a1_txs = tx_repo.find_by_account_id("a1")
    assert len(a1_txs) == 1
    assert a1_txs[0].transaction_type is TransactionType.TRANSFER_OUT
    assert a1_txs[0].amount == 500
