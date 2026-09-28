from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.services.manage import DefaultAccountManageService
from langgraph_mini.account.services.query import DefaultAccountQueryService
from langgraph_mini.account.services.transfer import DefaultAccountTransferService
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository
from langgraph_mini.agent.confirmation import ConfirmationDecision
from langgraph_mini.agent.graph import build_graph
from langgraph_mini.billing.repository import MemoryBillRepository
from langgraph_mini.billing.services.pay import DefaultBillPaymentService
from langgraph_mini.billing.services.query import DefaultBillingQueryService
from langgraph_mini.card.domain import Card, CardKind, CardStatus
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.reissue_request_repository import MemoryReissueRequestRepository
from langgraph_mini.card.services.query import DefaultCardQueryService
from langgraph_mini.card.services.reissue import DefaultCardReissueService
from langgraph_mini.card.services.status import DefaultCardStatusService
from langgraph_mini.orchestration.actions import Repos, Services, build_actions
from langgraph_mini.orchestration.completed_repository import MemoryCompletedRequestRepository
from langgraph_mini.orchestration.pending_repository import MemoryPendingRepository
from langgraph_mini.orchestration.service import OrchestrationService


def _build_orchestration():
    account_repo = MemoryAccountRepository()
    account_repo.save(Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000))
    transaction_repo = MemoryTransactionRepository()
    card_repo = MemoryCardRepository()
    card_repo.save(Card(card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK))
    reissue_repo = MemoryReissueRequestRepository()
    bill_repo = MemoryBillRepository()

    services = Services(
        account_query=DefaultAccountQueryService(account_repo, transaction_repo, card_repo),
        account_transfer=DefaultAccountTransferService(account_repo, transaction_repo),
        account_manage=DefaultAccountManageService(account_repo),
        card_query=DefaultCardQueryService(card_repo, account_repo),
        card_status=DefaultCardStatusService(card_repo),
        card_reissue=DefaultCardReissueService(card_repo, reissue_repo),
        billing_query=DefaultBillingQueryService(bill_repo),
        billing_payment=DefaultBillPaymentService(bill_repo, account_repo, transaction_repo),
    )
    repos = Repos(account=account_repo, card=card_repo, reissue_request=reissue_repo, bill=bill_repo)
    actions = build_actions(repos)
    orchestration = OrchestrationService(
        actions, services, MemoryPendingRepository(), MemoryCompletedRequestRepository()
    )
    return orchestration, card_repo


class _FakeLLM:
    """메인 에이전트 자리 대역 — bind_tools는 그냥 self를 반환하고,
    invoke는 미리 준비한 AIMessage를 순서대로 돌려줌."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._i = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        response = self._responses[self._i]
        self._i += 1
        return response


class _FakeStructuredLLM:
    def __init__(self, decision):
        self._decision = decision

    def invoke(self, prompt):
        return self._decision


class _FakeConfirmationLLM:
    def __init__(self, decision):
        self._decision = decision

    def with_structured_output(self, schema):
        return _FakeStructuredLLM(self._decision)


CONFIG = {"configurable": {"thread_id": "t1", "requester_id": "u1"}}


def test_propose_then_approve_end_to_end():
    orchestration, card_repo = _build_orchestration()
    propose_call = AIMessage(
        content="",
        tool_calls=[{"name": "block_card_as_lost", "args": {"card_id": "c1"}, "id": "call_1"}],
    )
    final_reply = AIMessage(content="카드를 분실 정지했습니다.")
    llm = _FakeLLM([propose_call, final_reply])
    app = build_graph(llm, orchestration, _FakeConfirmationLLM(ConfirmationDecision(action="approve")))

    result = app.invoke(
        {"messages": [HumanMessage(content="생활비 카드 잃어버렸어. 정지해줘.")]}, config=CONFIG
    )
    assert result.get("__interrupt__")
    assert card_repo.find_by_id("c1").status is CardStatus.USABLE  # 아직 승인 전

    result2 = app.invoke(Command(resume="응 진행해줘"), config=CONFIG)

    assert result2["messages"][-1].content == "카드를 분실 정지했습니다."
    assert card_repo.find_by_id("c1").status is CardStatus.LOST


def test_propose_then_reject_end_to_end():
    orchestration, card_repo = _build_orchestration()
    propose_call = AIMessage(
        content="",
        tool_calls=[{"name": "block_card_as_lost", "args": {"card_id": "c1"}, "id": "call_1"}],
    )
    final_reply = AIMessage(content="알겠습니다, 취소했어요.")
    llm = _FakeLLM([propose_call, final_reply])
    app = build_graph(llm, orchestration, _FakeConfirmationLLM(ConfirmationDecision(action="reject")))

    app.invoke({"messages": [HumanMessage(content="카드 정지해줘")]}, config=CONFIG)
    result = app.invoke(Command(resume="아니 취소할게"), config=CONFIG)

    assert result["messages"][-1].content == "알겠습니다, 취소했어요."
    assert card_repo.find_by_id("c1").status is CardStatus.USABLE


def test_query_only_turn_does_not_interrupt():
    orchestration, _ = _build_orchestration()
    query_call = AIMessage(
        content="", tool_calls=[{"name": "get_my_cards", "args": {}, "id": "call_q"}]
    )
    final_reply = AIMessage(content="카드가 1개 있어요.")
    llm = _FakeLLM([query_call, final_reply])
    app = build_graph(llm, orchestration, _FakeConfirmationLLM(ConfirmationDecision(action="approve")))

    result = app.invoke({"messages": [HumanMessage(content="내 카드 보여줘")]}, config=CONFIG)

    assert not result.get("__interrupt__")
    assert result["messages"][-1].content == "카드가 1개 있어요."


def test_recovery_after_restart_resolves_pending_without_reasking_llm():
    """프로세스 1: propose까지만 하고 "죽음". 프로세스 2: 완전히 새 그래프/체크포인터로
    다시 만들지만 orchestration은 그대로(=JSON 파일이 살아남은 상황을 흉내) — 새
    사용자 메시지만으로 그 자리에서 이어서 처리돼야 하고, 메인 에이전트 LLM은 이번
    턴에 한 번도 안 불려야 한다(복구가 agent 노드까지 안 가고 끝나야 하므로)."""
    orchestration, card_repo = _build_orchestration()

    propose_call = AIMessage(
        content="",
        tool_calls=[{"name": "block_card_as_lost", "args": {"card_id": "c1"}, "id": "call_1"}],
    )
    app1 = build_graph(
        _FakeLLM([propose_call]), orchestration, _FakeConfirmationLLM(ConfirmationDecision(action="approve"))
    )
    app1.invoke({"messages": [HumanMessage(content="카드 정지해줘")]}, config=CONFIG)
    assert card_repo.find_by_id("c1").status is CardStatus.USABLE

    # "재시작" — 완전히 새 그래프(새 InMemorySaver), 같은 orchestration
    llm2 = _FakeLLM([])  # 호출되면 즉시 IndexError로 터짐 → 안 불렸는지 검증하는 셈
    app2 = build_graph(llm2, orchestration, _FakeConfirmationLLM(ConfirmationDecision(action="approve")))

    result = app2.invoke({"messages": [HumanMessage(content="응 진행해줘")]}, config=CONFIG)

    assert card_repo.find_by_id("c1").status is CardStatus.LOST
    assert orchestration.get_pending("t1") == []
    assert result["messages"][-1].content.startswith("(재시작 후 이어서 처리)")


def test_recovery_ignores_unrelated_message_and_falls_through_to_agent():
    orchestration, card_repo = _build_orchestration()

    propose_call = AIMessage(
        content="",
        tool_calls=[{"name": "block_card_as_lost", "args": {"card_id": "c1"}, "id": "call_1"}],
    )
    app1 = build_graph(
        _FakeLLM([propose_call]), orchestration, _FakeConfirmationLLM(ConfirmationDecision(action="approve"))
    )
    app1.invoke({"messages": [HumanMessage(content="카드 정지해줘")]}, config=CONFIG)

    # 재시작 후 완전히 무관한 새 요청이 들어옴 — pending은 그대로 두고 agent가 처리해야 함
    unrelated_reply = AIMessage(content="오늘 날씨는 저도 몰라요!")
    app2 = build_graph(
        _FakeLLM([unrelated_reply]),
        orchestration,
        _FakeConfirmationLLM(ConfirmationDecision(action="unrelated")),
    )

    result = app2.invoke({"messages": [HumanMessage(content="오늘 날씨 어때?")]}, config=CONFIG)

    assert result["messages"][-1].content == "오늘 날씨는 저도 몰라요!"
    assert card_repo.find_by_id("c1").status is CardStatus.USABLE  # 여전히 대기 중
    assert len(orchestration.get_pending("t1")) == 1
