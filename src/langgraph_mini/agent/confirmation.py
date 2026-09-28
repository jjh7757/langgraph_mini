"""승인 루프 — propose_and_confirm/resume_and_confirm이 모든 실행형 tool의 공용 진입점.

request_id로는 tool_call_id를 그대로 쓴다(에이전트_설계.md 1절 참고) — interrupt() 재개 시
LangGraph가 그 노드/tool 함수를 처음부터 다시 실행하므로, request_id를 여기서 uuid4 같은 걸로
새로 만들면 재실행마다 값이 달라져 Orchestration의 멱등성이 깨진다. tool_call_id는 LLM의
tool call 자체에 붙는 값이라 재실행돼도 항상 같다.

`ask` 파라미터는 기본값이 실제 `langgraph.types.interrupt`이지만, 테스트에서는 그래프
없이 순수 함수로 검증할 수 있도록 아무 콜러블이나 넣을 수 있게 열어둠(DI).
"""

from typing import Callable, Literal

from langgraph.types import interrupt
from pydantic import BaseModel

from ..orchestration.domain import ActionResult, PendingRequest, PendingStatus
from ..orchestration.service import OrchestrationService
from .context import AgentContext

MAX_REVISIONS = 5  # 한 번의 확인 흐름 안에서 "수정"을 무한 반복하지 못하게 막는 상한


class ConfirmationDecision(BaseModel):
    action: Literal["approve", "reject", "revise", "unrelated"]
    new_params: dict | None = None  # action == "revise"일 때만 채움


def _summarize(request: PendingRequest, *, note: str | None = None) -> dict:
    """interrupt()로 사용자에게 보여줄 요약. note는 "이해 못 했다"처럼 재확인 사유를 덧붙일 때."""
    payload = {
        "request_id": request.request_id,
        "action": request.action,
        "params": request.params,
        "message": f"다음 내용을 진행할까요?\n{request.action}: {request.params}",
    }
    if note:
        payload["note"] = note
    return payload


def classify_confirmation(reply: str, request: PendingRequest, llm) -> ConfirmationDecision:
    """작은 구조화 출력 LLM 호출로 사용자의 raw 답변을 분류.

    llm은 `.with_structured_output(ConfirmationDecision)`을 지원하는 chat model이면 됨
    (메인 에이전트와 같은 모델을 재사용해도 되고, 더 싼 모델을 따로 둬도 됨 — 아직 안 정함,
    에이전트_설계.md 9절 참고).
    """
    structured_llm = llm.with_structured_output(ConfirmationDecision)
    prompt = (
        "다음은 사용자에게 승인을 요청한 작업과 그에 대한 사용자의 답변입니다. "
        "사용자의 답변을 분류하세요.\n\n"
        f"작업: {request.action}\n"
        f"파라미터: {request.params}\n"
        f"사용자 답변: {reply}\n\n"
        "분류 기준:\n"
        "- approve: 승인/진행 의사\n"
        "- reject: 거절/취소 의사\n"
        "- revise: 내용을 바꾸고 싶어함 — new_params에 바뀌는 필드만 담을 것\n"
        "- unrelated: 이 작업과 무관한 이야기"
    )
    return structured_llm.invoke(prompt)


def confirm_loop(
    request: PendingRequest,
    ctx: AgentContext,
    orchestration: OrchestrationService,
    llm,
    ask: Callable[[dict], str] = interrupt,
    initial_decision: ConfirmationDecision | None = None,
) -> ActionResult:
    """PENDING인 동안 반복: 물어보고 → 분류하고 → approve/reject/revise.

    revise면 params만 갱신하고 다시 처음부터 보여줌("승인 전 수정" — 전체 내용을 다시
    보여준 뒤 재승인). unrelated면 요청은 그대로 둔 채 다시 물어봄(무슨 뜻인지 못
    알아들었다는 note를 붙여서).

    `initial_decision`을 주면 첫 바퀴는 ask()/classify_confirmation을 건너뛰고 그
    결정을 바로 씀 — 재시작 복구 시(6절 참고) 사용자의 새 메시지가 이미 와 있는데
    또 물어보면 안 되므로, graph.py의 check_recovery가 그 메시지를 미리 분류해서
    넘겨줄 때 씀.
    """
    revisions = 0
    note: str | None = None
    decision = initial_decision

    while request.status is PendingStatus.PENDING:
        if decision is None:
            reply = ask(_summarize(request, note=note))
            decision = classify_confirmation(reply, request, llm)
        note = None

        if decision.action == "approve":
            return orchestration.approve(request.request_id)

        if decision.action == "reject":
            orchestration.reject(request.request_id)
            return ActionResult(
                success=False, error_type="Rejected", error_message="사용자가 거절함"
            )

        if decision.action == "revise":
            revisions += 1
            if revisions > MAX_REVISIONS:
                orchestration.reject(request.request_id)
                return ActionResult(
                    success=False,
                    error_type="TooManyRevisions",
                    error_message="수정 횟수 초과로 취소됨",
                )
            request = orchestration.revise(
                request.request_id, decision.new_params or {}, ctx.requester_id
            )
            decision = None
            continue

        # unrelated — 요청은 그대로 두고 다시 확인 요청
        note = "무슨 뜻인지 이해하지 못했어요. 승인/거절/수정 중 어떤 건가요?"
        decision = None

    return request.result


def propose_and_confirm(
    action: str,
    params: dict,
    ctx: AgentContext,
    request_id: str,
    orchestration: OrchestrationService,
    llm,
    ask: Callable[[dict], str] = interrupt,
) -> ActionResult:
    """새 제안 시작점. orchestration.propose() 후 그대로 confirm_loop로."""
    request = orchestration.propose(action, params, ctx.requester_id, ctx.thread_id, request_id)
    return confirm_loop(request, ctx, orchestration, llm, ask)


def resume_and_confirm(
    request: PendingRequest,
    ctx: AgentContext,
    orchestration: OrchestrationService,
    llm,
    ask: Callable[[dict], str] = interrupt,
    initial_decision: ConfirmationDecision | None = None,
) -> ActionResult:
    """재시작 복구용 — 이미 있는 PendingRequest를 propose 없이 confirm_loop로 바로 이어감."""
    return confirm_loop(request, ctx, orchestration, llm, ask, initial_decision)
