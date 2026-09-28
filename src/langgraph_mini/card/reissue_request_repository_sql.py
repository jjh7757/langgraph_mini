"""ReissueRequestRepository의 Postgres 구현체."""

from ..db.postgres import current_connection
from .domain import DeliveryAddress, ReissueRequest, ReissueRequestNotFoundError, ReissueStatus


class SqlReissueRequestRepository:
    def find_by_id(self, request_id: str) -> ReissueRequest:
        conn = current_connection()
        row = conn.execute(
            """
            SELECT request_id, card_id, delivery_address, status, created_at
            FROM reissue_requests WHERE request_id = %s FOR UPDATE
            """,
            (request_id,),
        ).fetchone()
        if row is None:
            raise ReissueRequestNotFoundError(request_id)
        return _to_reissue_request(row)

    def find_by_card_id(self, card_id: str) -> list[ReissueRequest]:
        conn = current_connection()
        rows = conn.execute(
            """
            SELECT request_id, card_id, delivery_address, status, created_at
            FROM reissue_requests WHERE card_id = %s
            """,
            (card_id,),
        ).fetchall()
        return [_to_reissue_request(row) for row in rows]

    def save(self, request: ReissueRequest) -> None:
        conn = current_connection()
        conn.execute(
            """
            INSERT INTO reissue_requests
                (request_id, card_id, delivery_address, status, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (request_id) DO UPDATE
                SET delivery_address = EXCLUDED.delivery_address,
                    status = EXCLUDED.status
            """,
            (
                request.request_id,
                request.card_id,
                request.delivery_address.value,
                request.status.value,
                request.created_at,
            ),
        )


def _to_reissue_request(row) -> ReissueRequest:
    request_id, card_id, delivery_address, status, created_at = row
    return ReissueRequest(
        request_id=request_id,
        card_id=card_id,
        delivery_address=DeliveryAddress(delivery_address),
        status=ReissueStatus(status),
        created_at=created_at,
    )
