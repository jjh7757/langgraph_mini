"""PendingRepository의 Redis 구현체.

승인 대기 중인 요청만 여기 산다(설계 결정 — 진행상황.md: "Redis는 PendingRepo 전용, 완료된
요청 이력은 Postgres에 영구 보관"). 그래서 save()가 PENDING이 아닌 상태로 불리면(즉
approve/reject 이후 재-save) 저장하는 대신 키를 지운다 — Postgres(completed_repo)가 이미
그 최종 상태를 영구 보관하므로 Redis엔 더 남아있을 이유가 없다.

json_codec.encode/decode를 그대로 재사용해 PendingRequest를 JSON 문자열로 직렬화한다(JSON
파일 구현체와 동일한 규칙). client는 decode_responses=True로 만들어졌다고 가정한다
(wiring.py에서 그렇게 생성).
"""

import json

import redis

from .. import json_codec as codec
from .domain import PendingRequest, PendingRequestNotFoundError, PendingStatus

_TTL_SECONDS = 24 * 60 * 60  # 방치된 승인 요청 안전망 — 24시간 지나면 자동 소멸


def _key(request_id: str) -> str:
    return f"pending:{request_id}"


def _thread_key(thread_id: str) -> str:
    return f"pending:thread:{thread_id}"


class RedisPendingRepository:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def find_by_id(self, request_id: str) -> PendingRequest:
        raw = self._client.get(_key(request_id))
        if raw is None:
            raise PendingRequestNotFoundError(request_id)
        return _decode(raw)

    def find_by_thread_id(self, thread_id: str) -> list[PendingRequest]:
        request_ids = self._client.smembers(_thread_key(thread_id))
        requests = []
        for request_id in request_ids:
            raw = self._client.get(_key(request_id))
            if raw is not None:  # TTL로 만료된 멤버는 조용히 건너뜀
                requests.append(_decode(raw))
        return requests

    def save(self, request: PendingRequest) -> None:
        thread_key = _thread_key(request.thread_id)
        if request.status is not PendingStatus.PENDING:
            self._client.delete(_key(request.request_id))
            self._client.srem(thread_key, request.request_id)
            return

        raw = json.dumps(codec.encode(request))
        self._client.set(_key(request.request_id), raw, ex=_TTL_SECONDS)
        self._client.sadd(thread_key, request.request_id)
        self._client.expire(thread_key, _TTL_SECONDS)


def _decode(raw: str) -> PendingRequest:
    return codec.decode(json.loads(raw))
