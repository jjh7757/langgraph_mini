"""실제 Gemini로 돌아가는 터미널 대화 진입점.

    uv run langgraph-mini                    (pyproject.toml [project.scripts])
    또는: uv run python -m langgraph_mini.cli

.env(또는 환경변수)에서 GOOGLE_API_KEY(또는 GEMINI_API_KEY)를 읽는다. data/*.json에
실제로 읽고 쓰며(agent.wiring.build_orchestration), 프로그램을 껐다 켜도 계좌 잔액·카드
상태·승인 대기 중이던 요청이 그대로 남아있다(재시작 복구 — 에이전트_설계.md 6절).

이 프로젝트엔 "계좌 개설" 같은 생성 기능이 없어서(기존 계좌/카드/청구서를 다루는 기능만
있음), data/ 가 비어있는 첫 실행에서는 가지고 놀 데이터가 없다 — 그래서 처음 한 번만
데모용 계좌·카드·청구서를 만들어둔다(_ensure_demo_data).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from .agent.demo_data import DEMO_OWNER_ID, ensure_demo_data
from .agent.graph import build_graph, extract_reply_text
from .agent.wiring import build_orchestration

DEFAULT_THREAD_ID = "default"

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    # Windows 콘솔 기본 코드페이지(cp949 등)로는 한글 이모지·특수문자 출력이 깨지거나
    # UnicodeEncodeError로 죽을 수 있어서 항상 UTF-8로 강제.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    # load_dotenv()는 인자가 없으면 상위 폴더까지 올라가며 .env를 찾는데, 부트캠프
    # 폴더처럼 다른 프로젝트의 .env가 상위에 있으면 그걸 잘못 읽어버릴 수 있어서
    # 이 프로젝트 루트의 .env로 경로를 명시.
    load_dotenv(PROJECT_ROOT / ".env")

    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        print(
            "GOOGLE_API_KEY(또는 GEMINI_API_KEY)가 설정돼 있지 않습니다.\n"
            "프로젝트 루트에 .env 파일을 만들고 다음처럼 넣어주세요:\n"
            "  GOOGLE_API_KEY=여기에_발급받은_키"
        )
        sys.exit(1)

    # langchain_google_genai는 모듈 임포트 시점이 아니라 호출 시점에 키를 읽으므로
    # 지연 임포트(여기서 처음 import) — API 키가 없을 때 불필요하게 무거운 임포트를
    # 안 하게 됨(위 sys.exit(1) 이후엔 아예 안 불림).
    from langchain_google_genai import ChatGoogleGenerativeAI

    data_dir = os.environ.get("LANGGRAPH_MINI_DATA_DIR", str(PROJECT_ROOT / "data"))
    _ensure_demo_data(data_dir)

    orchestration = build_orchestration(data_dir)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    # thinking_budget 기본값(-1, "동적")으로 두면 tool 22개 + system prompt를 한꺼번에
    # bind했을 때 모델이 thinking에 예산을 전부 써버리고 응답(tool_call도 없이) 없이
    # 끝나버리는 문제가 실제로 재현됨(고정 예산을 주면 해결됨 — 직접 확인).
    thinking_budget = int(os.environ.get("GEMINI_THINKING_BUDGET", "1024"))
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0, thinking_budget=thinking_budget)
    app = build_graph(llm, orchestration)

    thread_id = os.environ.get("LANGGRAPH_MINI_THREAD_ID", DEFAULT_THREAD_ID)
    config = {"configurable": {"thread_id": thread_id, "requester_id": DEMO_OWNER_ID}}

    print(f"langgraph-mini 데모 (모델: {model_name}, thread: {thread_id}). 종료: exit / quit")

    if orchestration.get_pending(thread_id):
        print("[이전에 처리하지 못한 요청이 남아있어요. 확인할게요]")
        _run_and_handle(app, config, {"messages": []})

    _repl(app, config)


def _repl(app, config) -> None:
    while True:
        try:
            text = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.lower() in {"exit", "quit"}:
            return
        if not text:
            continue
        _run_and_handle(app, config, {"messages": [HumanMessage(content=text)]})


def _run_and_handle(app, config, payload) -> None:
    """interrupt()가 나오면 그 자리에서 계속 물어보고 Command(resume=...)로 이어감."""
    from langgraph.types import Command

    result = app.invoke(payload, config=config)

    while result.get("__interrupt__"):
        question = result["__interrupt__"][0].value.get("message", "확인해주세요")
        print(f"봇> {question}")
        try:
            reply = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        result = app.invoke(Command(resume=reply), config=config)

    messages = result.get("messages") or []
    if messages:
        print(f"봇> {extract_reply_text(messages[-1].content)}")


def _ensure_demo_data(data_dir: str) -> None:
    """data/*.json이 비어있으면(처음 실행) 데모용 계좌 2개·카드 1개·청구서 1개를 만들어둔다.
    이미 데이터가 있으면 아무것도 안 함(owner_id 기준으로 확인) — 실제 로직은 API 앱과
    공유하는 agent/demo_data.py에 있음."""
    from .account.repository_json import JsonAccountRepository
    from .billing.repository_json import JsonBillRepository
    from .card.repository_json import JsonCardRepository

    path = Path(data_dir)
    created = ensure_demo_data(
        JsonAccountRepository(path / "accounts.json"),
        JsonCardRepository(path / "cards.json"),
        JsonBillRepository(path / "bills.json"),
        DEMO_OWNER_ID,
    )
    if created:
        print("[처음 실행 — 데모 데이터 생성: 계좌 2개(생활비/저축), 카드 1개, 청구서 1개]")


if __name__ == "__main__":
    main()
