"""도구 함수가 받는 RunnableConfig에서 requester_id/thread_id를 꺼내는 곳.

requester_id는 절대 LLM이 tool 인자로 넘기게 하지 않는다(그러면 LLM이 남의 id로
요청하는 걸 막을 방법이 없음) — 항상 그래프를 invoke할 때
config={"configurable": {"thread_id": ..., "requester_id": ...}}로 넘겨받은 값만 쓴다.
thread_id는 LangGraph checkpointer가 원래 쓰는 값과 같은 걸 그대로 재사용한다
(대화 스레드 = Orchestration의 thread_id, 따로 관리하지 않음).
"""

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig


class MissingContextError(Exception):
    """config.configurable에 requester_id/thread_id가 없을 때."""


@dataclass
class AgentContext:
    requester_id: str
    thread_id: str


def get_context(config: RunnableConfig) -> AgentContext:
    configurable = config.get("configurable", {})
    try:
        return AgentContext(
            requester_id=configurable["requester_id"],
            thread_id=configurable["thread_id"],
        )
    except KeyError as exc:
        raise MissingContextError(
            "config['configurable']에 requester_id/thread_id가 필요합니다"
        ) from exc
