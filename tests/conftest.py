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


@pytest.fixture
def api_client(monkeypatch):
    """api/app.py를 실제 TEST_DATABASE_URL/TEST_REDIS_URL로 통째로 띄운 TestClient.
    lifespan이 그대로 실행되므로(ensure_demo_data 포함) 매 테스트가 깨끗한 데모 데이터
    (demo-acc-1/2, demo-card-1, demo-bill-1)로 시작한다. GOOGLE_API_KEY는 빈 문자열로
    막아서(.env에 실제 키가 있어도 load_dotenv가 덮어쓰지 않음) 챗봇 그래프는 안 뜨게 한다
    — REST 엔드포인트 테스트엔 필요 없다."""
    if not TEST_DATABASE_URL or not TEST_REDIS_URL:
        pytest.skip(
            "TEST_DATABASE_URL/TEST_REDIS_URL not set — docker-compose.dev.yml로 로컬 "
            "Postgres/Redis를 띄워야 함"
        )

    import psycopg
    import redis

    connection = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
    connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    for table in _TABLES:
        connection.execute(f"TRUNCATE TABLE {table} CASCADE")
    connection.close()
    redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True).flushdb()

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("REDIS_URL", TEST_REDIS_URL)
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    from fastapi.testclient import TestClient

    from langgraph_mini.api.app import app

    with TestClient(app) as client:
        yield client
