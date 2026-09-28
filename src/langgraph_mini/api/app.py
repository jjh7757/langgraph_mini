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

from ..account.repository_sql import SqlAccountRepository
from ..agent.demo_data import DEMO_OWNER_ID, ensure_demo_data
from ..agent.graph import build_graph
from ..agent.wiring import build_orchestration_sql
from ..billing.repository_sql import SqlBillRepository
from ..card.repository_sql import SqlCardRepository
from ..db.postgres import create_pool, request_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = Path(__file__).resolve().parent / "static"

_state: dict = {"pool": None, "graph_app": None}
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
        orchestration = build_orchestration_sql(redis_client)
        _state["graph_app"] = build_graph(llm, orchestration)
    else:
        logger.warning(
            "GOOGLE_API_KEY/GEMINI_API_KEY가 없어 채팅 기능을 켜지 않았습니다 "
            "(헬스체크·정적 페이지는 정상 동작). .env 채운 뒤 재시작하세요."
        )

    yield

    pool.close()


app = FastAPI(lifespan=lifespan)


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
