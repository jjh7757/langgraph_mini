"""AccountRepository의 Postgres 구현체.

find_by_id는 SELECT ... FOR UPDATE로 행을 잠근다 — transfer()류가 잔액을 읽고 바꾼 뒤
저장하는 동안 동시 요청이 같은 계좌를 건드리지 못하게 막는다(Memory/JSON 구현체엔 이
동시성 제어가 전혀 없었음). 그래서 find_by_id는 항상 활성 트랜잭션
(db.postgres.request_transaction()) 안에서만 호출해야 한다.
"""

from ..db.postgres import current_connection
from .domain import Account, AccountNotFoundError


class SqlAccountRepository:
    def find_by_id(self, account_id: str) -> Account:
        conn = current_connection()
        row = conn.execute(
            "SELECT account_id, owner_id, nickname, balance FROM accounts "
            "WHERE account_id = %s FOR UPDATE",
            (account_id,),
        ).fetchone()
        if row is None:
            raise AccountNotFoundError(account_id)
        return _to_account(row)

    def find_all(self) -> list[Account]:
        conn = current_connection()
        rows = conn.execute(
            "SELECT account_id, owner_id, nickname, balance FROM accounts"
        ).fetchall()
        return [_to_account(row) for row in rows]

    def find_by_owner_id(self, owner_id: str) -> list[Account]:
        conn = current_connection()
        rows = conn.execute(
            "SELECT account_id, owner_id, nickname, balance FROM accounts WHERE owner_id = %s",
            (owner_id,),
        ).fetchall()
        return [_to_account(row) for row in rows]

    def save(self, account: Account) -> None:
        conn = current_connection()
        conn.execute(
            """
            INSERT INTO accounts (account_id, owner_id, nickname, balance)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (account_id) DO UPDATE
                SET owner_id = EXCLUDED.owner_id,
                    nickname = EXCLUDED.nickname,
                    balance = EXCLUDED.balance
            """,
            (account.account_id, account.owner_id, account.nickname, account.balance),
        )


def _to_account(row) -> Account:
    account_id, owner_id, nickname, balance = row
    return Account(account_id=account_id, owner_id=owner_id, nickname=nickname, balance=balance)
