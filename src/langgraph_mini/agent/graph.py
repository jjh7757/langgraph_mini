"""StateGraph 조립.

    START
      → check_recovery   (get_pending(thread_id) 확인 — 재시작·장애 복구)
           남은 PENDING 있고 새 메시지가 그거랑 관련 있으면 → resume_and_confirm()으로
             그 자리에서 이어서 처리하고 END
           없거나(PENDING 없음) 새 메시지가 무관(unrelated)하면 →
      → agent            (LLM + 22개 tool bind, 평소 ReAct 루프)
           tool 호출 필요 → tools(ToolNode, 그 안에서 필요하면 tool이 스스로 interrupt())
             → 다시 agent로
           아니면 → END

checkpointer는 지금 단계에서 InMemorySaver(휘발성)로 충분하다 — 이유는
에이전트_설계.md 6절 참고("재시작 복구"의 정확성은 checkpointer가 아니라 이미 JSON으로
저장되는 Orchestration의 PendingRepo가 담당함).
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from ..orchestration.service import OrchestrationService
from .confirmation import classify_confirmation, resume_and_confirm
from .context import get_context
from .propose_tools import build_tools

RECOVERY_PREFIX = "(재시작 후 이어서 처리)"

SYSTEM_PROMPT = (
    "당신은 은행 업무를 도와주는 어시스턴트입니다. 계좌·카드·청구서 조회는 바로 답하고, "
    "잔액이나 상태를 바꾸는 요청은 반드시 tool을 통해 사용자 승인을 받은 뒤에만 처리하세요. "
    "요청에 필요한 정보(계좌/카드/금액 등)가 빠졌으면 tool을 호출하지 말고 먼저 되물으세요. "
    "어떤 계좌/카드를 말하는지 불분명하면(별명이 여러 개거나 대명사로만 지칭) 조회 tool로 "
    "후보를 찾아 사용자에게 골라달라고 하세요."
)


def build_graph(llm, orchestration: OrchestrationService, confirmation_llm=None):
    """llm: 메인 에이전트가 쓸 chat model(.bind_tools 지원).
    confirmation_llm: 승인 루프의 자연어 분류에 쓸 chat model(.with_structured_output 지원).
    생략하면 llm을 그대로 재사용(에이전트_설계.md 9절 — 아직 안 정한 것)."""
    confirmation_llm = confirmation_llm or llm
    tools = build_tools(orchestration, confirmation_llm)
    llm_with_tools = llm.bind_tools(tools)

    def check_recovery(state: MessagesState, config):
        """재시작·장애 복구. PENDING이 남아있으면:
        - 이번에 새로 온 사용자 메시지가 없으면(어쩌다 빈 호출) 곧바로 다시 물어봄(interrupt)
        - 있으면 그 메시지를 먼저 한 번 분류해서, 이 pending과 무관(unrelated)하면 그대로 두고
          평소 에이전트 흐름으로 넘김(agent 노드가 새 메시지를 처리) — 관련 있으면 그
          분류 결과로 바로 confirm_loop를 이어감(같은 메시지를 또 물어보지 않음)."""
        ctx = get_context(config)
        pending = orchestration.get_pending(ctx.thread_id)
        if not pending:
            return {}

        # 여러 건이 있으면(원래는 드묾) 가장 먼저 만들어진 것부터 하나씩 처리
        request = min(pending, key=lambda r: r.created_at)
        reply = _latest_human_text(state["messages"])

        if reply is None:
            result = resume_and_confirm(request, ctx, orchestration, confirmation_llm)
            return {"messages": [AIMessage(content=_recovery_summary(request, result))]}

        decision = classify_confirmation(reply, request, confirmation_llm)
        if decision.action == "unrelated":
            return {}

        result = resume_and_confirm(
            request, ctx, orchestration, confirmation_llm, initial_decision=decision
        )
        return {"messages": [AIMessage(content=_recovery_summary(request, result))]}

    def recovery_was_handled(state: MessagesState) -> bool:
        last = state["messages"][-1] if state["messages"] else None
        return isinstance(last, AIMessage) and last.content.startswith(RECOVERY_PREFIX)

    def agent(state: MessagesState):
        response = llm_with_tools.invoke(_with_system_prompt(state["messages"]))
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("check_recovery", check_recovery)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "check_recovery")
    graph.add_conditional_edges(
        "check_recovery",
        lambda state: END if recovery_was_handled(state) else "agent",
        {"agent": "agent", END: END},
    )
    graph.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=InMemorySaver())


def _latest_human_text(messages: list) -> str | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content
    return None


def _recovery_summary(request, result) -> str:
    return f"{RECOVERY_PREFIX} {request.action}: {result}"


def _with_system_prompt(messages: list) -> list:
    if messages and isinstance(messages[0], SystemMessage):
        return messages
    return [SystemMessage(content=SYSTEM_PROMPT), *messages]


def _route_after_agent(state: MessagesState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END
