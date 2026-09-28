"""CompletedRequestRepository의 Postgres 구현체.

params/result는 action마다 모양이 다르고 중첩 dataclass(ActionResult,
ConditionalTransferQuote 등)까지 들어가서 정규 컬럼 대신 JSONB + 기존
json_codec.encode/decode를 그대로 재사용한다 — JSON 파일 구현체와 동일한 직렬화 규칙이라
Postgres/JSON 사이에서 인코딩이 갈라지지 않는다.
"""

from psycopg.types.json import Jsonb

from .. import json_codec as codec
from ..db.postgres import current_connection
from .domain import PendingRequest, PendingStatus


class SqlCompletedRequestRepository:
    def find_by_request_id(self, request_id: str) -> PendingRequest | None:
        conn = current_connection()
        row = conn.execute(
            """
            SELECT request_id, thread_id, requester_id, action, params, status, result,
                   created_at, resolved_at
            FROM completed_requests WHERE request_id = %s
            """,
            (request_id,),
        ).fetchone()
        return None if row is None else _to_request(row)

    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]:
        conn = current_connection()
        rows = conn.execute(
            """
            SELECT request_id, thread_id, requester_id, action, params, status, result,
                   created_at, resolved_at
            FROM completed_requests WHERE thread_id = %s
            """,
            (thread_id,),
        ).fetchall()
        return [_to_request(row) for row in rows]

    def save(self, request: PendingRequest) -> None:
        conn = current_connection()
        conn.execute(
            """
            INSERT INTO completed_requests
                (request_id, thread_id, requester_id, action, params, status, result,
                 created_at, resolved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (request_id) DO UPDATE
                SET status = EXCLUDED.status,
                    params = EXCLUDED.params,
                    result = EXCLUDED.result,
                    resolved_at = EXCLUDED.resolved_at
            """,
            (
                request.request_id,
                request.thread_id,
                request.requester_id,
                request.action,
                Jsonb(codec.encode(request.params)),
                request.status.value,
                Jsonb(codec.encode(request.result)) if request.result is not None else None,
                request.created_at,
                request.resolved_at,
            ),
        )


def _to_request(row) -> PendingRequest:
    (
        request_id,
        thread_id,
        requester_id,
        action,
        params,
        status,
        result,
        created_at,
        resolved_at,
    ) = row
    return PendingRequest(
        request_id=request_id,
        thread_id=thread_id,
        requester_id=requester_id,
        action=action,
        params=codec.decode(params),
        status=PendingStatus(status),
        result=codec.decode(result) if result is not None else None,
        created_at=created_at,
        resolved_at=resolved_at,
    )
