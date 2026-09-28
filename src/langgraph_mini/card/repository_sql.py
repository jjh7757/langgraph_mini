"""CardRepository의 Postgres 구현체. find_by_id는 SELECT ... FOR UPDATE로 잠근다 —
AccountRepository.find_by_id와 같은 이유(status 전이 전 동시 요청 차단)."""

from ..db.postgres import current_connection
from .domain import Card, CardKind, CardNotFoundError, CardStatus


class SqlCardRepository:
    def find_by_id(self, card_id: str) -> Card:
        conn = current_connection()
        row = conn.execute(
            "SELECT card_id, account_id, name, kind, status FROM cards "
            "WHERE card_id = %s FOR UPDATE",
            (card_id,),
        ).fetchone()
        if row is None:
            raise CardNotFoundError(card_id)
        return _to_card(row)

    def find_by_account_id(self, account_id: str) -> list[Card]:
        conn = current_connection()
        rows = conn.execute(
            "SELECT card_id, account_id, name, kind, status FROM cards WHERE account_id = %s",
            (account_id,),
        ).fetchall()
        return [_to_card(row) for row in rows]

    def save(self, card: Card) -> None:
        conn = current_connection()
        conn.execute(
            """
            INSERT INTO cards (card_id, account_id, name, kind, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (card_id) DO UPDATE
                SET account_id = EXCLUDED.account_id,
                    name = EXCLUDED.name,
                    kind = EXCLUDED.kind,
                    status = EXCLUDED.status
            """,
            (card.card_id, card.account_id, card.name, card.kind.value, card.status.value),
        )


def _to_card(row) -> Card:
    card_id, account_id, name, kind, status = row
    return Card(
        card_id=card_id,
        account_id=account_id,
        name=name,
        kind=CardKind(kind),
        status=CardStatus(status),
    )
