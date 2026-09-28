"""Postgres 커넥션 풀 + "현재 트랜잭션" contextvar.

왜 커넥션을 contextvar로 넘기는가: agent/graph.py의 InMemorySaver 체크포인터는 그래프 객체
하나가 프로세스 내내 유지돼야 같은 대화의 여러 턴(HTTP 요청 여러 번)에 걸쳐 문맥이 이어진다
(CLI가 app = build_graph(...)를 한 번만 만들어 REPL 내내 재사용하는 것과 동일한 이유). 반면
DB 쓰기는 요청 하나(에이전트 한 턴, tool을 여러 번 호출할 수 있음) 단위로 트랜잭션이 걸려야
transfer()의 계좌 2개 저장, pay_bills()의 청구서별 3저장 같은 다중 저장이 원자적으로 처리된다.

그래프(따라서 그 안의 orchestration/repos)를 요청마다 새로 만들면 체크포인터가 리셋되고,
반대로 Sql*Repository가 생성자로 커넥션을 받으면 그래프도 요청마다 새로 만들어야 해서 위와
충돌한다 — 그래서 Sql*Repository는 인자 없이 한 번만 생성해서 그래프에 물리고, 실제 커넥션은
이 모듈의 contextvar을 통해 요청마다 주입한다.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar

import psycopg
from psycopg_pool import ConnectionPool

_current_conn: ContextVar[psycopg.Connection | None] = ContextVar("_current_conn", default=None)


def create_pool(dsn: str, *, min_size: int = 1, max_size: int = 5) -> ConnectionPool:
    """min/max를 작게 유지한다 — 공용 Postgres 컨테이너를 여러 앱이 max_connections=50으로
    나눠 쓰므로(DB환경구성.md), 앱 하나가 기본 풀 크기(20~30)를 그대로 쓰면 다른 앱 배포 때
    다른 앱의 연결이 거부될 수 있다."""
    return ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=True)


@contextlib.contextmanager
def request_transaction(pool: ConnectionPool):
    """요청(에이전트 한 턴) 전체를 감싸는 트랜잭션 경계. 성공 시 자동 commit, 예외 시 자동
    rollback(psycopg3 conn.transaction()의 기본 동작). API 레이어가 app.invoke() 호출 하나를
    이 블록으로 감싸면, 그 안에서 일어나는 모든 Sql*Repository.save()가 하나의 트랜잭션으로
    묶인다."""
    with pool.connection() as conn:
        with conn.transaction():
            with bind_connection(conn):
                yield conn


@contextlib.contextmanager
def bind_connection(conn: psycopg.Connection):
    """이미 열려 있는 커넥션을 현재 컨텍스트에 직접 물린다(풀에서 새로 꺼내지 않음).
    request_transaction()과 달리 트랜잭션 시작/커밋은 관리하지 않는다 — 호출한 쪽이 책임짐.
    테스트에서 커넥션 하나의 트랜잭션 경계를 직접 제어하고 싶을 때 쓴다."""
    token = _current_conn.set(conn)
    try:
        yield conn
    finally:
        _current_conn.reset(token)


def current_connection() -> psycopg.Connection:
    conn = _current_conn.get()
    if conn is None:
        raise RuntimeError(
            "활성 DB 트랜잭션이 없습니다 — request_transaction()/bind_connection() 블록 "
            "안에서만 Sql*Repository를 호출할 수 있습니다"
        )
    return conn
