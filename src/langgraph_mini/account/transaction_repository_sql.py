"""TransactionRepository의 Postgres 구현체. append-only 엔티티라 락이 필요 없다(수정 없이
추가만 함 — id 없는 도메인 모델에 surrogate PK만 SQL 쪽에 추가, 디코드 시 무시)."""

from ..db.postgres import current_connection
from .domain import Transaction, TransactionType


class SqlTransactionRepository:
    def save(self, transaction: Transaction) -> None:
        conn = current_connection()
        conn.execute(
            """
            INSERT INTO transactions
                (account_id, transaction_type, amount, counterpart_id, card_id, bill_id,
                 created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                transaction.account_id,
                transaction.transaction_type.value,
                transaction.amount,
                transaction.counterpart_id,
                transaction.card_id,
                transaction.bill_id,
                transaction.created_at,
            ),
        )

    def find_by_account_id(self, account_id: str) -> list[Transaction]:
        conn = current_connection()
        rows = conn.execute(
            """
            SELECT account_id, transaction_type, amount, counterpart_id, card_id, bill_id,
                   created_at
            FROM transactions WHERE account_id = %s
            """,
            (account_id,),
        ).fetchall()
        return [_to_transaction(row) for row in rows]


def _to_transaction(row) -> Transaction:
    account_id, transaction_type, amount, counterpart_id, card_id, bill_id, created_at = row
    return Transaction(
        account_id=account_id,
        transaction_type=TransactionType(transaction_type),
        amount=amount,
        counterpart_id=counterpart_id,
        card_id=card_id,
        bill_id=bill_id,
        created_at=created_at,
    )
