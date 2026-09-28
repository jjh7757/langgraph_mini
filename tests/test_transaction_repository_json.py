from langgraph_mini.account.domain import Transaction, TransactionType
from langgraph_mini.account.transaction_repository_json import JsonTransactionRepository


def test_save_then_find_by_account_id(tmp_path):
    repo = JsonTransactionRepository(tmp_path / "transactions.json")
    tx = Transaction(
        account_id="a1",
        transaction_type=TransactionType.TRANSFER_OUT,
        amount=1000,
        counterpart_id="a2",
    )

    repo.save(tx)

    assert repo.find_by_account_id("a1") == [tx]


def test_find_by_account_id_returns_empty_list_when_none(tmp_path):
    repo = JsonTransactionRepository(tmp_path / "transactions.json")

    assert repo.find_by_account_id("no-such-account") == []


def test_data_survives_reopening_the_repository(tmp_path):
    path = tmp_path / "transactions.json"
    repo = JsonTransactionRepository(path)
    repo.save(
        Transaction(
            account_id="a1",
            transaction_type=TransactionType.CARD_PAYMENT,
            amount=5000,
            card_id="c1",
        )
    )

    reopened = JsonTransactionRepository(path)

    transactions = reopened.find_by_account_id("a1")
    assert len(transactions) == 1
    assert transactions[0].transaction_type is TransactionType.CARD_PAYMENT
    assert transactions[0].card_id == "c1"
