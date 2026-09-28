-- langgraph_mini Postgres 스키마. 서버에서 1회 적용:
--   docker exec -i postgres psql -U <role> -d <db> < schema.sql
-- Enum은 json_codec.py와 동일하게 .value(한글 문자열)를 VARCHAR로 저장한다 — 네이티브
-- Postgres ENUM 타입은 값 추가/변경 시 마이그레이션이 번거로워 이 규모에선 안 쓴다.
-- money(balance/amount)는 도메인이 이미 "float 금지, 원 단위 정수"를 강제하므로 BIGINT.
--
-- 참고: 두 계좌 사이의 반대 방향 동시 이체(A->B, B->A)가 겹치면 SELECT ... FOR UPDATE
-- 잠금 순서가 엇갈려 데드락이 날 수 있다 — 이 규모(데모)에서는 Postgres가 자동으로
-- 감지해 한쪽 트랜잭션을 에러로 중단시키는 것으로 충분하다고 보고 별도 처리는 하지 않았다.

CREATE TABLE IF NOT EXISTS accounts (
    account_id  TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    nickname    TEXT NOT NULL,
    balance     BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accounts_owner_id ON accounts (owner_id);

CREATE TABLE IF NOT EXISTS transactions (
    id               BIGSERIAL PRIMARY KEY,
    account_id       TEXT NOT NULL REFERENCES accounts (account_id),
    transaction_type VARCHAR(20) NOT NULL,
    amount           BIGINT NOT NULL,
    counterpart_id   TEXT,
    card_id          TEXT,
    bill_id          TEXT,
    created_at       TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions (account_id);

CREATE TABLE IF NOT EXISTS cards (
    card_id     TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL REFERENCES accounts (account_id),
    name        TEXT NOT NULL,
    kind        VARCHAR(10) NOT NULL,
    status      VARCHAR(10) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_account_id ON cards (account_id);

CREATE TABLE IF NOT EXISTS reissue_requests (
    request_id       TEXT PRIMARY KEY,
    card_id          TEXT NOT NULL REFERENCES cards (card_id),
    delivery_address VARCHAR(10) NOT NULL,
    status           VARCHAR(10) NOT NULL,
    created_at       TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reissue_requests_card_id ON reissue_requests (card_id);

CREATE TABLE IF NOT EXISTS bills (
    bill_id   TEXT PRIMARY KEY,
    owner_id  TEXT NOT NULL,
    name      TEXT NOT NULL,
    amount    BIGINT NOT NULL,
    due_date  DATE NOT NULL,
    status    VARCHAR(10) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bills_owner_id ON bills (owner_id);

-- 완료된(승인/거절/실패) 요청의 영구 이력. params/result는 액션마다 모양이 다르고
-- 중첩 dataclass(ActionResult, ConditionalTransferQuote 등)까지 들어가서 JSONB +
-- json_codec.encode/decode로 처리한다(orchestration/completed_repository_sql.py 참고).
CREATE TABLE IF NOT EXISTS completed_requests (
    request_id    TEXT PRIMARY KEY,
    thread_id     TEXT NOT NULL,
    requester_id  TEXT NOT NULL,
    action        TEXT NOT NULL,
    params        JSONB NOT NULL,
    status        VARCHAR(10) NOT NULL,
    result        JSONB,
    created_at    TIMESTAMP NOT NULL,
    resolved_at   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_completed_requests_thread_id ON completed_requests (thread_id);
