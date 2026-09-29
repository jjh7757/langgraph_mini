import json

from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository import MemoryAccountRepository
from langgraph_mini.account.services.manage import DefaultAccountManageService
from langgraph_mini.account.services.query import DefaultAccountQueryService
from langgraph_mini.account.services.transfer import DefaultAccountTransferService
from langgraph_mini.account.transaction_repository import MemoryTransactionRepository
from langgraph_mini.agent.propose_tools import build_tools
from langgraph_mini.billing.repository import MemoryBillRepository
from langgraph_mini.billing.services.pay import DefaultBillPaymentService
from langgraph_mini.billing.services.query import DefaultBillingQueryService
from langgraph_mini.card.domain import Card, CardKind
from langgraph_mini.card.repository import MemoryCardRepository
from langgraph_mini.card.reissue_request_repository import MemoryReissueRequestRepository
from langgraph_mini.card.services.query import DefaultCardQueryService
from langgraph_mini.card.services.reissue import DefaultCardReissueService
from langgraph_mini.card.services.status import DefaultCardStatusService
from langgraph_mini.orchestration.actions import Repos, Services, build_actions
from langgraph_mini.orchestration.completed_repository import MemoryCompletedRequestRepository
from langgraph_mini.orchestration.pending_repository import MemoryPendingRepository
from langgraph_mini.orchestration.service import OrchestrationService


def _build():
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
    return orchestration


def _tools_by_name(orchestration):
    tools = build_tools(orchestration, confirmation_llm=object())
    return {t.name: t for t in tools}


def test_build_tools_returns_22_tools_excluding_rest_only_action():
    # actions.py의 ACTIONS는 23개(account.list_recipients 포함)지만, list_recipients는
    # REST API 전용 조회라 챗봇 tool로는 안 만들어서 22개만 나와야 함.
    tools = _tools_by_name(_build())
    assert len(tools) == 22
    assert "list_recipients" not in tools


def test_execution_tools_hide_tool_call_id_and_config_from_llm_schema():
    tools = _tools_by_name(_build())
    schema = tools["block_card_as_lost"].tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"card_id"}


def test_query_tools_hide_config_from_llm_schema():
    tools = _tools_by_name(_build())
    schema = tools["get_account"].tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"account_id"}


def test_get_account_tool_returns_account_info():
    tools = _tools_by_name(_build())
    config = {"configurable": {"requester_id": "u1", "thread_id": "t1"}}

    output = tools["get_account"].invoke({"account_id": "a1"}, config=config)

    data = json.loads(output)
    assert data["balance"] == 1000
    assert data["nickname"] == "생활비"


def test_get_my_cards_tool_uses_requester_id_from_context_not_llm():
    tools = _tools_by_name(_build())
    config = {"configurable": {"requester_id": "u1", "thread_id": "t1"}}

    output = tools["get_my_cards"].invoke({}, config=config)

    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["card_id"] == "c1"


def test_get_my_cards_tool_raises_not_owner_for_other_users_cards():
    tools = _tools_by_name(_build())
    config = {"configurable": {"requester_id": "u2", "thread_id": "t1"}}

    output = tools["get_my_cards"].invoke({}, config=config)

    assert json.loads(output) == []  # u2는 카드가 없으니 빈 목록(자기 목록만 봄)
