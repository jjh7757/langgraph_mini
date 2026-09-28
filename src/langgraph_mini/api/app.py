"""웹 채팅 배포용 진입점 (uvicorn langgraph_mini.api.app:app).

cli.py의 _repl/_run_and_handle과 완전히 같은 흐름(app.invoke → __interrupt__ 있으면
Command(resume=...)로 이어감)을 HTTP 요청/응답 왕복에 맞게 나눈 것뿐 — agent/graph.py,
confirmation.py, propose_tools.py, context.py는 전혀 건드리지 않는다.

그래프(graph_app)는 프로세스 시작 시 딱 한 번 만들어 그대로 재사용한다 — InMemorySaver
체크포인터가 같은 대화의 여러 HTTP 요청에 걸쳐 문맥을 유지하려면 그래프 객체 자체가
프로세스 내내 살아있어야 하기 때문이다(db/postgres.py 모듈 docstring 참고). 대신 DB
쓰기는 요청(한 턴)마다 request_transaction()으로 감싸 트랜잭션 경계를 만든다.
"""

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import redis
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

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

    from langchain_google_genai import ChatGoogleGenerativeAI

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    orchestration = build_orchestration_sql(redis_client)

    _state["pool"] = pool
    _state["graph_app"] = build_graph(llm, orchestration)

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
    config = {"configurable": {"thread_id": thread_id, "requester_id": DEMO_OWNER_ID}}
    graph_app = _state["graph_app"]

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
