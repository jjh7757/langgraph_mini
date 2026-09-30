"""Agent 실행 하네스 — 사례마다 격리된 초기 데이터로 그래프를 돌리고 평가에 필요한 기록을 모은다.

노트북의 `run_agent`/`trajectory_target`에 해당한다. 이 프로젝트에 맞춘 차이:
- 승인이 자연어 답변이라 `Command(resume={interrupt_id: 답변 문장})`으로 재개한다.
- 초기 데이터는 임시 파일 복사가 아니라 Memory 저장소에 `ensure_demo_data()`로 채운다
  (사례마다 새로 만들므로 서로 영향이 없다).
- 실행 뒤 저장소를 직접 읽은 `snapshot()`을 함께 반환해서 `state_check`가 실제 잔액·상태를 본다.
"""

import json
from dataclasses import dataclass
from uuid import uuid4

from langchain_core.tracers.context import collect_runs
from langgraph.types import Command
from langsmith import traceable

from langgraph_mini.account.domain import Account, Transaction, TransactionType
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.services.manage import DefaultAccountManageService
from langgraph_mini.account.services.query import DefaultAccountQueryService
from langgraph_mini.account.services.transfer import DefaultAccountTransferService
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository
from langgraph_mini.agent.demo_data import DEMO_OWNER_ID, ensure_demo_data
from langgraph_mini.agent.graph import build_graph, extract_reply_text
from langgraph_mini.billing.repository import MemoryBillRepository
from langgraph_mini.billing.services.pay import DefaultBillPaymentService
from langgraph_mini.billing.services.query import DefaultBillingQueryService
from langgraph_mini.card.domain import DeliveryAddress, ReissueRequest
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.reissue_request_repository import MemoryReissueRequestRepository
from langgraph_mini.card.services.query import DefaultCardQueryService
from langgraph_mini.card.services.reissue import DefaultCardReissueService
from langgraph_mini.card.services.status import DefaultCardStatusService
from langgraph_mini.orchestration.actions import Repos, Services, build_actions
from langgraph_mini.orchestration.completed_repository import MemoryCompletedRequestRepository
from langgraph_mini.orchestration.pending_repository import MemoryPendingRepository
from langgraph_mini.orchestration.service import OrchestrationService

CARD_ID = "demo-card-1"
BILL_ID = "demo-bill-1"
ACC_LIFE = "demo-acc-1"
ACC_SAVE = "demo-acc-2"


@dataclass
class Env:
    orchestration: OrchestrationService
    account_repo: MemoryAccountRepository
    transaction_repo: MemoryTransactionRepository
    card_repo: MemoryCardRepository
    bill_repo: MemoryBillRepository
    reissue_repo: MemoryReissueRequestRepository


# ── 시드 (평가/평가_목록.md 2절) ──────────────────────────────────────


def _seed_s0(env: Env) -> None:
    """기본 데모 데이터 — build_env가 이미 채워 둠."""


def _seed_s1(env: Env) -> None:
    card = env.card_repo.find_by_id(CARD_ID)
    card.block_as_lost()
    env.card_repo.save(card)


def _seed_s2(env: Env) -> None:
    _seed_s1(env)
    env.reissue_repo.save(
        ReissueRequest(request_id="reissue-1", card_id=CARD_ID, delivery_address=DeliveryAddress.HOME)
    )


def _seed_s3(env: Env) -> None:
    env.account_repo.save(
        Account(account_id="demo-acc-5", owner_id=DEMO_OWNER_ID, nickname="여행 자금", balance=300000)
    )


def _seed_s4(env: Env) -> None:
    bill = env.bill_repo.find_by_id(BILL_ID)
    bill.pay()
    env.bill_repo.save(bill)


def _seed_s5(env: Env) -> None:
    for amount in (30000, 200000):
        env.transaction_repo.save(
            Transaction(
                account_id=ACC_LIFE,
                transaction_type=TransactionType.TRANSFER_OUT,
                amount=amount,
                counterpart_id=ACC_SAVE,
            )
        )


def _seed_s6(env: Env) -> None:
    card = env.card_repo.find_by_id(CARD_ID)
    card.lock_temporarily()
    env.card_repo.save(card)


SEEDS = {
    "S0": _seed_s0,
    "S1": _seed_s1,
    "S2": _seed_s2,
    "S3": _seed_s3,
    "S4": _seed_s4,
    "S5": _seed_s5,
    "S6": _seed_s6,
}
SEED_NAMES = tuple(SEEDS)


def build_env(seed: str) -> Env:
    """새 Memory 저장소에 데모 데이터를 채우고 시드를 적용한 독립 환경."""
    if seed not in SEEDS:
        raise ValueError(f"알 수 없는 시드: {seed} (가능: {SEED_NAMES})")

    account_repo = MemoryAccountRepository()
    transaction_repo = MemoryTransactionRepository()
    card_repo = MemoryCardRepository()
    reissue_repo = MemoryReissueRequestRepository()
    bill_repo = MemoryBillRepository()
    ensure_demo_data(account_repo, card_repo, bill_repo)

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
    orchestration = OrchestrationService(
        build_actions(repos), services, MemoryPendingRepository(), MemoryCompletedRequestRepository()
    )
    env = Env(orchestration, account_repo, transaction_repo, card_repo, bill_repo, reissue_repo)
    SEEDS[seed](env)
    return env


def snapshot(env: Env) -> dict:
    """실행 결과 확인용으로 저장소를 직접 읽은 JSON 직렬화 가능한 요약."""
    accounts = env.account_repo.find_all()
    cards = [card for account in accounts for card in env.card_repo.find_by_account_id(account.account_id)]
    return {
        "accounts": {account.account_id: account.balance for account in accounts},
        "cards": {card.card_id: card.status.value for card in cards},
        "bills": {bill.bill_id: bill.status.value for bill in env.bill_repo.find_by_owner_id(DEMO_OWNER_ID)},
        "reissue_by_card": {
            card.card_id: [
                {
                    "request_id": request.request_id,
                    "delivery_address": request.delivery_address.value,
                    "status": request.status.value,
                }
                for request in env.reissue_repo.find_by_card_id(card.card_id)
            ]
            for card in cards
        },
    }


# ── Tool 실행 기록 수집 ───────────────────────────────────────────────


def recorded_tools(roots) -> list:
    """LangChain 실행 기록 트리에서 Tool 실행만 시작 시각순으로 모은다."""
    runs = {}

    def visit(run):
        runs[run.id] = run
        for child in run.child_runs:
            visit(child)

    for root in roots:
        visit(root)
    return sorted((run for run in runs.values() if run.run_type == "tool"), key=lambda run: run.start_time)


def tool_calls_from(roots) -> list[dict]:
    """실행된 Tool 목록. interrupt가 걸린 Tool은 중단 시점과 재개 후 재실행 두 번 기록되므로
    (name, args)가 같은 기록은 첫 번째만 남긴다."""
    calls, seen = [], set()
    for run in recorded_tools(roots):
        args = {
            key: value
            for key, value in run.inputs.items()
            if key not in ("runtime", "config") and value is not None
        }
        signature = (run.name, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        if signature in seen:
            continue
        seen.add(signature)
        calls.append({"id": str(run.id), "name": run.name, "args": args})
    return calls


# ── 실행 ──────────────────────────────────────────────────────────────


def make_target(llm, confirmation_llm=None, *, recursion_limit: int = 40):
    """LangSmith `client.evaluate()`에 넘길 target 함수를 만든다.

    llm/confirmation_llm은 실제 chat model이거나(평가), 테스트용 대역이다.
    반환 함수는 inputs(seed/question/replies)를 받아 answer, approval, state, tool_calls를 돌려준다.
    """

    @traceable(name="langgraph-mini-evaluation")
    def run_agent(inputs: dict) -> dict:
        env = build_env(inputs["seed"])
        app = build_graph(llm, env.orchestration, confirmation_llm)
        # 새 thread_id로 다른 사례의 대화·승인 상태와 분리한다. requester_id는 사용자 입력이 아니라
        # config로만 전달한다(agent/context.py의 설계 원칙).
        config = {
            "configurable": {"thread_id": str(uuid4()), "requester_id": DEMO_OWNER_ID},
            "recursion_limit": recursion_limit,
        }
        initial_state = snapshot(env)
        replies = iter(inputs["replies"])
        # interrupt ID는 수정(revise)처럼 같은 Tool 안에서 다시 물을 때 재사용되므로 ID로 세지 않고,
        # 우리가 처리(재개 또는 대기로 종료)한 중단마다 한 번씩 기록한다.
        interrupt_actions: list[str] = []
        used_replies: list[str] = []

        result = app.invoke({"messages": [("user", inputs["question"])]}, config=config)
        while result.get("__interrupt__"):
            pending = result["__interrupt__"][0]
            interrupt_actions.append(pending.value.get("action"))
            reply = next(replies, None)
            # 준비한 답변이 없으면 승인 대기를 남긴 채 종료한다(approval_flow가 실패로 채점).
            if reply is None:
                break
            used_replies.append(reply)
            result = app.invoke(Command(resume={pending.id: reply}), config=config)

        approval_pending = bool(result.get("__interrupt__"))
        return {
            "answer": "" if approval_pending else extract_reply_text(result["messages"][-1].content),
            "approval": {
                "interrupt_count": len(interrupt_actions),
                "actions": interrupt_actions,
                "used_replies": used_replies,
                "pending": approval_pending,
            },
            "initial_state": initial_state,
            "state": snapshot(env),
        }

    def target(inputs: dict) -> dict:
        # 블록 안의 실행 기록을 메모리에 모은다(최초 실행과 승인 후 재개 모두 포함).
        with collect_runs() as traces:
            result = run_agent(inputs)
        result["tool_calls"] = tool_calls_from(traces.traced_runs)
        return result

    return target
