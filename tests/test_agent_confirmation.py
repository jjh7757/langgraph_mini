from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.services.manage import DefaultAccountManageService
from langgraph_mini.account.services.query import DefaultAccountQueryService
from langgraph_mini.account.services.transfer import DefaultAccountTransferService
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository
from langgraph_mini.agent.confirmation import (
    ConfirmationDecision,
    confirm_loop,
    propose_and_confirm,
    resume_and_confirm,
)
from langgraph_mini.agent.context import AgentContext
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
from langgraph_mini.orchestration.domain import PendingStatus
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


class _FakeStructuredLLM:
    def __init__(self, decisions):
        self._decisions = list(decisions)
        self._i = 0

    def invoke(self, prompt):
        decision = self._decisions[self._i]
        self._i += 1
        return decision


class _FakeLLM:
    """classify_confirmation이 부르는 llm.with_structured_output(...).invoke(prompt) 흉내.
    decisions 리스트를 순서대로 하나씩 돌려줌(호출될 때마다 하나씩 소비)."""

    def __init__(self, decisions):
        self._structured = _FakeStructuredLLM(decisions)

    def with_structured_output(self, schema):
        return self._structured


def _asker(replies):
    """confirm_loop의 ask 콜러블 대역 — interrupt() 없이 replies를 순서대로 반환."""
    it = iter(replies)
    return lambda payload: next(it)


CTX = AgentContext(requester_id="u1", thread_id="t1")


def test_propose_and_confirm_approves_and_executes():
    orchestration, card_repo = _build_orchestration()
    llm = _FakeLLM([ConfirmationDecision(action="approve")])

    result = propose_and_confirm(
        "card.block_as_lost", {"card_id": "c1"}, CTX, "req-1", orchestration, llm,
        ask=_asker(["네 진행해줘"]),
    )

    assert result.success is True
    assert card_repo.find_by_id("c1").status is CardStatus.LOST


def test_propose_and_confirm_rejects_without_executing():
    orchestration, card_repo = _build_orchestration()
    llm = _FakeLLM([ConfirmationDecision(action="reject")])

    result = propose_and_confirm(
        "card.block_as_lost", {"card_id": "c1"}, CTX, "req-1", orchestration, llm,
        ask=_asker(["아니 취소할게"]),
    )

    assert result.success is False
    assert result.error_type == "Rejected"
    assert card_repo.find_by_id("c1").status is CardStatus.USABLE


def test_propose_and_confirm_revises_then_approves():
    orchestration, _ = _build_orchestration()
    llm = _FakeLLM(
        [
            ConfirmationDecision(action="revise", new_params={"card_id": "c1"}),
            ConfirmationDecision(action="approve"),
        ]
    )

    result = propose_and_confirm(
        "card.block_as_lost", {"card_id": "c1"}, CTX, "req-1", orchestration, llm,
        ask=_asker(["아니 잠깐만", "이제 진행해"]),
    )

    assert result.success is True


def test_propose_and_confirm_reasks_on_unrelated_reply():
    orchestration, card_repo = _build_orchestration()
    llm = _FakeLLM(
        [ConfirmationDecision(action="unrelated"), ConfirmationDecision(action="approve")]
    )

    result = propose_and_confirm(
        "card.block_as_lost", {"card_id": "c1"}, CTX, "req-1", orchestration, llm,
        ask=_asker(["오늘 날씨 어때", "응 승인"]),
    )

    assert result.success is True
    assert card_repo.find_by_id("c1").status is CardStatus.LOST


def test_too_many_revisions_gives_up_and_rejects():
    orchestration, card_repo = _build_orchestration()
    decisions = [ConfirmationDecision(action="revise", new_params={"card_id": "c1"})] * 10
    llm = _FakeLLM(decisions)

    result = propose_and_confirm(
        "card.block_as_lost", {"card_id": "c1"}, CTX, "req-1", orchestration, llm,
        ask=_asker(["또 바꿔줘"] * 10),
    )

    assert result.success is False
    assert result.error_type == "TooManyRevisions"
    assert card_repo.find_by_id("c1").status is CardStatus.USABLE


def test_resume_and_confirm_continues_existing_pending_request():
    orchestration, card_repo = _build_orchestration()
    request = orchestration.propose(
        "card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "req-1"
    )
    llm = _FakeLLM([ConfirmationDecision(action="approve")])

    result = resume_and_confirm(request, CTX, orchestration, llm, ask=_asker(["네"]))

    assert result.success is True
    assert card_repo.find_by_id("c1").status is CardStatus.LOST


def test_confirm_loop_with_initial_decision_skips_first_ask():
    orchestration, card_repo = _build_orchestration()
    request = orchestration.propose(
        "card.block_as_lost", {"card_id": "c1"}, "u1", "t1", "req-1"
    )
    llm = _FakeLLM([])  # ask()가 호출되면 안 되니 분류 호출도 없어야 함

    def _should_not_be_called(payload):
        raise AssertionError("initial_decision이 있으면 ask()가 불리면 안 됨")

    result = confirm_loop(
        request, CTX, orchestration, llm,
        ask=_should_not_be_called,
        initial_decision=ConfirmationDecision(action="approve"),
    )

    assert result.success is True
    assert card_repo.find_by_id("c1").status is CardStatus.LOST


def test_propose_and_confirm_is_idempotent_when_called_again_with_same_request_id():
    orchestration, card_repo = _build_orchestration()
    llm = _FakeLLM([ConfirmationDecision(action="approve")])

    propose_and_confirm(
        "card.block_as_lost", {"card_id": "c1"}, CTX, "req-1", orchestration, llm,
        ask=_asker(["네"]),
    )

    # 같은 request_id로 다시 호출해도(예: LangGraph의 interrupt 재실행) 재실행 안 되고
    # 이미 끝난 결과를 그대로 돌려줌 — ask가 다시 호출되면 안 됨(completed에서 바로 반환)
    def _should_not_be_called(payload):
        raise AssertionError("이미 완료된 request_id는 다시 물어보면 안 됨")

    result = propose_and_confirm(
        "card.block_as_lost", {"card_id": "c1"}, CTX, "req-1", orchestration, llm,
        ask=_should_not_be_called,
    )

    assert result.success is True
