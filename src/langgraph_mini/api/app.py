"""웹 채팅 배포용 진입점 (uvicorn langgraph_mini.api.app:app).

cli.py의 _repl/_run_and_handle과 완전히 같은 흐름(app.invoke → __interrupt__ 있으면
Command(resume=...)로 이어감)을 HTTP 요청/응답 왕복에 맞게 나눈 것뿐 — agent/graph.py,
confirmation.py, propose_tools.py, context.py는 전혀 건드리지 않는다.

그래프(graph_app)는 프로세스 시작 시 딱 한 번 만들어 그대로 재사용한다 — InMemorySaver
체크포인터가 같은 대화의 여러 HTTP 요청에 걸쳐 문맥을 유지하려면 그래프 객체 자체가
프로세스 내내 살아있어야 하기 때문이다(db/postgres.py 모듈 docstring 참고). 대신 DB
쓰기는 요청(한 턴)마다 request_transaction()으로 감싸 트랜잭션 경계를 만든다.
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import redis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from ..account.domain import AccountNotFoundError, DuplicateNicknameError, InsufficientBalanceError
from ..account.repository_sql import SqlAccountRepository
from ..account.services.transfer import (
    AccountSelfTransferError,
    ConditionalTransferNotNeededError,
    StaleConditionalTransferError,
)
from ..agent.demo_data import DEMO_OWNER_ID, ensure_demo_data
from ..agent.graph import build_graph
from ..agent.wiring import build_orchestration_sql
from ..billing.domain import BillAlreadyPaidError, BillNotFoundError
from ..billing.repository_sql import SqlBillRepository
from ..card.domain import (
    CardAlreadyLostError,
    CardNotFoundError,
    CardNotLockedError,
    CardNotLostError,
    CardNotUsableError,
    DeliveryAddress,
    ReissueRequestAlreadyExistsError,
    ReissueRequestNotFoundError,
    ReissueRequestNotModifiableError,
)
from ..card.repository_sql import SqlCardRepository
from ..db.postgres import create_pool, request_transaction
from ..orchestration.domain import (
    ActionNotRegisteredError,
    MissingParamsError,
    NotOwnerError,
    PendingRequestNotFoundError,
    PendingRequestNotPendingError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = Path(__file__).resolve().parent / "static"

_state: dict = {"pool": None, "graph_app": None, "orchestration": None}
# thread_id -> 현재 interrupt() 응답 대기 중인지. 순수 최적화용 — 재배포로 날아가도
# 안전하다: graph.py의 check_recovery 노드가 재시작 후 orchestration의 durable pending
# 상태를 다시 읽어 스스로 복구하므로, 이 세트가 비어 있어도 다음 메시지가 check_recovery를
# 거쳐 올바르게 이어진다.
_interrupted_threads: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(PROJECT_ROOT / ".env")

    pool = create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=5)
    redis_client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

    with request_transaction(pool):
        ensure_demo_data(SqlAccountRepository(), SqlCardRepository(), SqlBillRepository())

    _state["pool"] = pool

    # 대시보드/계좌/카드/청구서 REST 엔드포인트는 LLM과 무관하게 항상 필요하므로
    # GOOGLE_API_KEY 유무와 상관없이 먼저 조립해둔다 (에이전트가 쓰는 것과 완전히 같은
    # OrchestrationService 인스턴스 — Agent(챗봇)와 REST가 같은 승인/소유권 검증 경로를 씀).
    orchestration = build_orchestration_sql(redis_client)
    _state["orchestration"] = orchestration

    # GOOGLE_API_KEY/GEMINI_API_KEY가 없으면 여기서 죽지 않게 함 — DB 마이그레이션이나
    # 배포 파이프라인 점검처럼 LLM 없이도 헬스체크(GET /)는 확인하고 싶을 때가 있어서,
    # 없으면 경고만 남기고 graph_app을 None으로 둔다(채팅 엔드포인트가 503으로 안내).
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        # cli.py와 동일한 이유로 thinking_budget을 고정 — 기본값(-1, "동적")이면 tool 22개
        # + system prompt를 한꺼번에 bind했을 때 모델이 thinking에 예산을 전부 써버리고
        # 응답 없이 끝나버리는 문제가 실제로 재현됨(cli.py 주석 참고).
        thinking_budget = int(os.environ.get("GEMINI_THINKING_BUDGET", "1024"))
        llm = ChatGoogleGenerativeAI(
            model=model_name, temperature=0, thinking_budget=thinking_budget
        )
        _state["graph_app"] = build_graph(llm, orchestration)
    else:
        logger.warning(
            "GOOGLE_API_KEY/GEMINI_API_KEY가 없어 채팅 기능을 켜지 않았습니다 "
            "(헬스체크·정적 페이지는 정상 동작). .env 채운 뒤 재시작하세요."
        )

    yield

    pool.close()


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# REST(비-챗봇) 화면용 엔드포인트 — 대시보드/전체계좌/카드관리/청구서 화면이 씀.
# 전부 agent/graph.py의 tool들과 완전히 같은 OrchestrationService(_state["orchestration"])를
# 호출한다: 조회는 query(), 실행은 propose()+approve()를 REST 요청 하나 안에서 바로 이어서
# 호출(run_action) — 이미 화면 쪽 "확인" 단계가 사람의 승인 역할을 하므로 별도 승인
# 엔드포인트를 안 둠. request_id는 매 호출마다 새로 생성한다(REST에는 LangGraph의
# interrupt-재실행이 없어 tool_call_id 재사용 같은 멱등성 요구가 없음).
# ---------------------------------------------------------------------------

# ActionResult.error_type(예외 클래스 이름) → 사용자에게 보여줄 한글 메시지.
_ERROR_MESSAGES: dict[str, str] = {
    "AccountNotFoundError": "계좌를 찾을 수 없습니다.",
    "InsufficientBalanceError": "잔액이 부족합니다.",
    "DuplicateNicknameError": "이미 사용 중인 별명입니다.",
    "AccountSelfTransferError": "같은 계좌로는 이체할 수 없습니다.",
    "ConditionalTransferNotNeededError": "조건에 맞는 이체 금액이 없습니다.",
    "StaleConditionalTransferError": "그 사이 잔액이 바뀌어 다시 확인이 필요합니다.",
    "CardNotFoundError": "카드를 찾을 수 없습니다.",
    "CardAlreadyLostError": "이미 분실 처리된 카드입니다.",
    "CardNotUsableError": "지금 상태에서는 잠글 수 없습니다.",
    "CardNotLockedError": "잠금 상태가 아니어서 해제할 수 없습니다.",
    "CardNotLostError": "분실 처리된 카드만 재발급 신청할 수 있습니다.",
    "ReissueRequestAlreadyExistsError": "이미 진행 중인 재발급 신청이 있습니다.",
    "ReissueRequestNotFoundError": "재발급 신청 내역을 찾을 수 없습니다.",
    "ReissueRequestNotModifiableError": "이미 진행되어 변경·취소할 수 없습니다.",
    "BillNotFoundError": "청구서를 찾을 수 없습니다.",
    "BillAlreadyPaidError": "이미 납부된 청구서입니다.",
}

_NOT_FOUND_ERRORS = (
    AccountNotFoundError,
    CardNotFoundError,
    BillNotFoundError,
    ReissueRequestNotFoundError,
    PendingRequestNotFoundError,
)
_BAD_REQUEST_ERRORS = (
    InsufficientBalanceError,
    DuplicateNicknameError,
    AccountSelfTransferError,
    ConditionalTransferNotNeededError,
    StaleConditionalTransferError,
    CardAlreadyLostError,
    CardNotUsableError,
    CardNotLockedError,
    CardNotLostError,
    ReissueRequestAlreadyExistsError,
    ReissueRequestNotModifiableError,
    BillAlreadyPaidError,
    MissingParamsError,
    PendingRequestNotPendingError,
)


async def _domain_error_handler(request, exc: Exception) -> JSONResponse:
    if isinstance(exc, _NOT_FOUND_ERRORS):
        status_code = 404
    elif isinstance(exc, NotOwnerError):
        status_code = 403
    elif isinstance(exc, _BAD_REQUEST_ERRORS):
        status_code = 400
    else:  # ActionNotRegisteredError 등 — 프로그래밍 오류
        status_code = 500
    message = _ERROR_MESSAGES.get(type(exc).__name__, "요청을 처리할 수 없습니다.")
    return JSONResponse(status_code=status_code, content={"detail": message})


for _exc_type in (*_NOT_FOUND_ERRORS, NotOwnerError, *_BAD_REQUEST_ERRORS, ActionNotRegisteredError):
    app.add_exception_handler(_exc_type, _domain_error_handler)


def _account_dict(a) -> dict:
    return {"account_id": a.account_id, "owner_id": a.owner_id, "nickname": a.nickname, "balance": a.balance}


def _card_dict(c) -> dict:
    return {
        "card_id": c.card_id,
        "account_id": c.account_id,
        "name": c.name,
        "kind": c.kind.value,
        "status": c.status.name,  # USABLE/LOCKED/LOST — 프론트가 분기하기 쉽게 name 사용
    }


def _bill_dict(b) -> dict:
    return {
        "bill_id": b.bill_id,
        "owner_id": b.owner_id,
        "name": b.name,
        "amount": b.amount,
        "due_date": b.due_date.isoformat(),
        "status": b.status.name,  # UNPAID/PAID
    }


def _transaction_view_dict(v) -> dict:
    t = v.transaction
    return {
        "transaction_type": t.transaction_type.name,  # TRANSFER_OUT/TRANSFER_IN/CARD_PAYMENT/BILL_PAYMENT
        "amount": t.amount,
        "counterpart_id": t.counterpart_id,
        "card_id": t.card_id,
        "bill_id": t.bill_id,
        "created_at": t.created_at.isoformat(),
        "card": _card_dict(v.card) if v.card else None,
    }


def _reissue_request_dict(r) -> dict:
    return {
        "request_id": r.request_id,
        "card_id": r.card_id,
        "delivery_address": r.delivery_address.name,  # HOME/WORK
        "status": r.status.name,
        "created_at": r.created_at.isoformat(),
    }


def _run_action(action: str, params: dict):
    """propose() 후 같은 요청 안에서 바로 approve() — 화면의 "확인" 단계가 이미 사람의
    승인 역할을 하므로 별도 승인 엔드포인트 없이 한 번에 실행한다. 실패(ActionResult.success
    False)면 400으로 변환해서 던짐. propose() 자체가 던지는 예외(NotOwnerError 등)는
    위 _domain_error_handler가 잡는다."""
    orchestration = _state["orchestration"]
    request_id = str(uuid.uuid4())
    pending = orchestration.propose(
        action, params, requester_id=DEMO_OWNER_ID, thread_id=f"rest-{request_id}", request_id=request_id
    )
    result = orchestration.approve(pending.request_id)
    if not result.success:
        message = _ERROR_MESSAGES.get(result.error_type, result.error_message or "요청을 처리할 수 없습니다.")
        raise HTTPException(status_code=400, detail=message)
    return result.value


class ChatMessage(BaseModel):
    message: str


@app.get("/")
def health() -> dict:
    return {"status": "ok"}


@app.get("/chat")
def chat_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "chat.html")


@app.post("/api/session")
def new_session() -> dict:
    return {"thread_id": str(uuid.uuid4())}


@app.post("/api/chat/{thread_id}")
def chat(thread_id: str, body: ChatMessage) -> JSONResponse:
    graph_app = _state["graph_app"]
    if graph_app is None:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_API_KEY가 설정되지 않아 채팅 기능을 쓸 수 없습니다. "
            "서버 .env를 채운 뒤 재시작해주세요.",
        )

    config = {"configurable": {"thread_id": thread_id, "requester_id": DEMO_OWNER_ID}}

    with request_transaction(_state["pool"]):
        if thread_id in _interrupted_threads:
            result = graph_app.invoke(Command(resume=body.message), config=config)
        else:
            result = graph_app.invoke(
                {"messages": [HumanMessage(content=body.message)]}, config=config
            )

    if result.get("__interrupt__"):
        _interrupted_threads.add(thread_id)
        question = result["__interrupt__"][0].value.get("message", "확인해주세요")
        return JSONResponse({"reply": question, "waiting_for_confirmation": True})

    _interrupted_threads.discard(thread_id)
    messages = result.get("messages") or []
    reply = messages[-1].content if messages else ""
    return JSONResponse({"reply": reply, "waiting_for_confirmation": False})


# ---------------------------------------------------------------------------
# 조회 (승인 불필요 — orchestration.query() 즉시 실행)
# ---------------------------------------------------------------------------


@app.get("/api/accounts")
def list_accounts() -> list[dict]:
    orchestration = _state["orchestration"]
    with request_transaction(_state["pool"]):
        accounts = orchestration.query(
            "account.get_accounts", {"owner_id": DEMO_OWNER_ID}, requester_id=DEMO_OWNER_ID
        )
    return [_account_dict(a) for a in accounts]


@app.get("/api/accounts/{account_id}/transactions")
def list_transactions(account_id: str) -> list[dict]:
    orchestration = _state["orchestration"]
    with request_transaction(_state["pool"]):
        views = orchestration.query(
            "account.get_transactions", {"account_id": account_id}, requester_id=DEMO_OWNER_ID
        )
    return [_transaction_view_dict(v) for v in views]


@app.get("/api/cards")
def list_cards() -> list[dict]:
    orchestration = _state["orchestration"]
    with request_transaction(_state["pool"]):
        cards = orchestration.query(
            "card.get_cards", {"owner_id": DEMO_OWNER_ID}, requester_id=DEMO_OWNER_ID
        )
    return [_card_dict(c) for c in cards]


@app.get("/api/bills")
def list_bills() -> list[dict]:
    orchestration = _state["orchestration"]
    with request_transaction(_state["pool"]):
        bills = orchestration.query(
            "billing.get_unpaid_bills", {"owner_id": DEMO_OWNER_ID}, requester_id=DEMO_OWNER_ID
        )
    return [_bill_dict(b) for b in bills]


# ---------------------------------------------------------------------------
# 실행 (propose+approve — 화면의 "확인" 단계가 승인 역할)
# ---------------------------------------------------------------------------


class TransferBody(BaseModel):
    from_id: str
    to_id: str
    amount: int


@app.post("/api/transfer")
def transfer(body: TransferBody) -> list[dict]:
    """받는사람은 항상 요청자 소유의 다른 계좌여야 함 — 이 프로젝트엔 계좌 개설/외부
    수취인 등록 기능이 없어서 실제로 존재하는 계좌끼리만 이체 가능(계좌 화면에서
    "내 다른 계좌"만 받는사람으로 보여주는 이유)."""
    with request_transaction(_state["pool"]):
        _run_action(
            "account.transfer",
            {"from_id": body.from_id, "to_id": body.to_id, "amount": body.amount},
        )
        orchestration = _state["orchestration"]
        accounts = orchestration.query(
            "account.get_accounts", {"owner_id": DEMO_OWNER_ID}, requester_id=DEMO_OWNER_ID
        )
    return [_account_dict(a) for a in accounts]


@app.post("/api/cards/{card_id}/lost")
def card_report_lost(card_id: str) -> dict:
    with request_transaction(_state["pool"]):
        card = _run_action("card.block_as_lost", {"card_id": card_id})
    return _card_dict(card)


@app.post("/api/cards/{card_id}/lock")
def card_lock(card_id: str) -> dict:
    with request_transaction(_state["pool"]):
        card = _run_action("card.lock_temporarily", {"card_id": card_id})
    return _card_dict(card)


@app.post("/api/cards/{card_id}/unlock")
def card_unlock(card_id: str) -> dict:
    with request_transaction(_state["pool"]):
        card = _run_action("card.unlock", {"card_id": card_id})
    return _card_dict(card)


class ReissueBody(BaseModel):
    delivery_address: str  # "HOME" | "WORK"


@app.post("/api/cards/{card_id}/reissue")
def card_reissue(card_id: str, body: ReissueBody) -> dict:
    try:
        delivery_address = DeliveryAddress[body.delivery_address]
    except KeyError:
        raise HTTPException(status_code=400, detail="배송지는 HOME 또는 WORK여야 합니다.")

    with request_transaction(_state["pool"]):
        reissue_request = _run_action(
            "card.request_reissue",
            {
                "card_id": card_id,
                "delivery_address": delivery_address,
                "request_id": str(uuid.uuid4()),
            },
        )
    return _reissue_request_dict(reissue_request)


class PayBillBody(BaseModel):
    account_id: str


@app.post("/api/bills/{bill_id}/pay")
def pay_bill(bill_id: str, body: PayBillBody) -> dict:
    with request_transaction(_state["pool"]):
        payment = _run_action(
            "billing.pay_bill", {"bill_id": bill_id, "account_id": body.account_id}
        )
        orchestration = _state["orchestration"]
        account = orchestration.query(
            "account.get_account", {"account_id": body.account_id}, requester_id=DEMO_OWNER_ID
        )
    return {"bill": _bill_dict(payment.bill), "account": _account_dict(account)}


class PayBillsBody(BaseModel):
    account_id: str
    bill_ids: list[str]


@app.post("/api/bills/pay-all")
def pay_bills(body: PayBillsBody) -> dict:
    with request_transaction(_state["pool"]):
        attempts = _run_action(
            "billing.pay_bills", {"account_id": body.account_id, "bill_ids": body.bill_ids}
        )
        orchestration = _state["orchestration"]
        account = orchestration.query(
            "account.get_account", {"account_id": body.account_id}, requester_id=DEMO_OWNER_ID
        )
    return {
        "attempts": [{"bill_id": a.bill_id, "outcome": a.outcome.name} for a in attempts],
        "account": _account_dict(account),
    }
