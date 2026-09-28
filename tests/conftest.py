"""SQL/Redis 레포지토리 테스트 공용 픽스처.

TEST_DATABASE_URL/TEST_REDIS_URL 환경변수가 없으면 해당 픽스처를 쓰는 테스트는 건너뜀
(로컬에서 `docker compose -f docker-compose.dev.yml up -d` 후 그 값을 넣어야 실행됨).
"""

import os
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL")

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "langgraph_mini" / "db" / "schema.sql"

# 외래키 의존 순서를 신경 쓸 필요 없이 한 번에 비우기 위해 CASCADE 사용
_TABLES = ["reissue_requests", "cards", "transactions", "accounts", "bills", "completed_requests"]


@pytest.fixture
def pg_conn():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set — docker-compose.dev.yml로 로컬 Postgres를 띄워야 함")

    import psycopg

    from langgraph_mini.db.postgres import bind_connection

    connection = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
    connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    for table in _TABLES:
        connection.execute(f"TRUNCATE TABLE {table} CASCADE")
    connection.autocommit = False

    with connection.transaction(), bind_connection(connection):
        yield connection

    connection.close()


@pytest.fixture
def redis_client():
    if not TEST_REDIS_URL:
        pytest.skip("TEST_REDIS_URL not set — docker-compose.dev.yml로 로컬 Redis를 띄워야 함")

    import redis

    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
