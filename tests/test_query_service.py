from datetime import date, timedelta

from langgraph_mini.account.card_repository import MemoryCardRepository
from langgraph_mini.account.domain import (
    Account,
    Card,
    Transaction,
    TransactionFilter,
    TransactionType,
)
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.services.query import DefaultAccountQueryService
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository


def _service():
    account_repo = MemoryAccountRepository()
    tx_repo = MemoryTransactionRepository()
    card_repo = MemoryCardRepository()
    return DefaultAccountQueryService(account_repo, tx_repo, card_repo), account_repo, tx_repo, card_repo


def test_get_account_returns_saved_account():
    service, account_repo, _, _ = _service()
    account = Account(account_id="a1", owner_id="u1", nickname="life", balance=1000)
    account_repo.save(account)

    assert service.get_account("a1") == account


def test_get_accounts_returns_only_owners_accounts():
    service, account_repo, _, _ = _service()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="life", balance=1000))
    account_repo.save(Account(account_id="a2", owner_id="u1", nickname="save", balance=500))
    account_repo.save(Account(account_id="a3", owner_id="u2", nickname="travel", balance=200))

    accounts = service.get_accounts("u1")

    assert {a.account_id for a in accounts} == {"a1", "a2"}


def test_get_total_balance_sums_multiple_accounts():
    service, account_repo, _, _ = _service()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="life", balance=1000))
    account_repo.save(Account(account_id="a2", owner_id="u1", nickname="save", balance=500))

    assert service.get_total_balance("u1") == 1500


def test_get_total_balance_is_zero_when_no_accounts():
    service, _, _, _ = _service()
    assert service.get_total_balance("nobody") == 0


def test_get_transactions_sorted_by_recent_first():
    service, _, tx_repo, _ = _service()
    older = Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=100)
    newer = Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_IN, amount=200)
    tx_repo.save(older)
    tx_repo.save(newer)

    views = service.get_transactions("a1")

    assert [v.transaction.amount for v in views] == [200, 100]


def test_get_transactions_enriches_card_payment_with_card():
    service, _, tx_repo, card_repo = _service()
    card_repo.save(Card(card_id="c1", account_id="a1", name="국민 체크카드"))
    tx_repo.save(
        Transaction(
            account_id="a1",
            transaction_type=TransactionType.CARD_PAYMENT,
            amount=30000,
            card_id="c1",
        )
    )

    views = service.get_transactions("a1")

    assert views[0].card is not None
    assert views[0].card.name == "국민 체크카드"


def test_get_transactions_filters_by_min_amount():
    service, _, tx_repo, _ = _service()
    tx_repo.save(Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=10000))
    tx_repo.save(Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=50000))

    views = service.get_transactions("a1", TransactionFilter(min_amount=40000))

    assert len(views) == 1
    assert views[0].transaction.amount == 50000


def test_get_transactions_filters_by_date_range():
    service, _, tx_repo, _ = _service()
    tx_repo.save(Transaction(account_id="a1", transaction_type=TransactionType.TRANSFER_OUT, amount=100))

    today = date.today()
    within_range = service.get_transactions(
        "a1", TransactionFilter(start_date=today, end_date=today)
    )
    outside_range = service.get_transactions(
        "a1",
        TransactionFilter(
            start_date=today - timedelta(days=10), end_date=today - timedelta(days=1)
        ),
    )

    assert len(within_range) == 1
    assert len(outside_range) == 0
