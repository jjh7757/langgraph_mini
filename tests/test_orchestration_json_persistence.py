"""JSON 저장소로 조립한 OrchestrationService가 실제로 "재시작 복구"를 만족하는지 확인.

Memory 대신 Json 구현체를 전부 써서 orchestration/actions.py의 build_actions()가
protocol만 보고 동작한다는 것과, 프로세스가 새로 뜬 것처럼 저장소를 다시 열어도
승인 대기 중이던 요청을 그대로 찾아 이어서 처리할 수 있다는 것을 함께 검증한다.
"""

from langgraph_mini.account.domain import Account
from langgraph_mini.account.repository_json import JsonAccountRepository
from langgraph_mini.account.services.manage import DefaultAccountManageService
from langgraph_mini.account.services.query import DefaultAccountQueryService
from langgraph_mini.account.services.transfer import DefaultAccountTransferService
from langgraph_mini.account.transaction_repository_json import JsonTransactionRepository
from langgraph_mini.billing.repository_json import JsonBillRepository
from langgraph_mini.billing.services.pay import DefaultBillPaymentService
from langgraph_mini.billing.services.query import DefaultBillingQueryService
from langgraph_mini.card.domain import Card, CardKind, CardStatus
from langgraph_mini.card.repository_json import JsonCardRepository
from langgraph_mini.card.reissue_request_repository_json import JsonReissueRequestRepository
from langgraph_mini.card.services.query import DefaultCardQueryService
from langgraph_mini.card.services.reissue import DefaultCardReissueService
from langgraph_mini.card.services.status import DefaultCardStatusService
from langgraph_mini.orchestration.actions import Repos, Services, build_actions
from langgraph_mini.orchestration.completed_repository_json import JsonCompletedRequestRepository
from langgraph_mini.orchestration.domain import PendingStatus
from langgraph_mini.orchestration.pending_repository_json import JsonPendingRepository
from langgraph_mini.orchestration.service import OrchestrationService


def _build_orchestration(paths):
    account_repo = JsonAccountRepository(paths["accounts"])
    transaction_repo = JsonTransactionRepository(paths["transactions"])
    card_repo = JsonCardRepository(paths["cards"])
    reissue_repo = JsonReissueRequestRepository(paths["reissue_requests"])
    bill_repo = JsonBillRepository(paths["bills"])

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

    pending_repo = JsonPendingRepository(paths["pending"])
    completed_repo = JsonCompletedRequestRepository(paths["completed"])

    return OrchestrationService(actions, services, pending_repo, completed_repo), card_repo


def _paths(tmp_path):
    return {
        "accounts": tmp_path / "accounts.json",
        "transactions": tmp_path / "transactions.json",
        "cards": tmp_path / "cards.json",
        "reissue_requests": tmp_path / "reissue_requests.json",
        "bills": tmp_path / "bills.json",
        "pending": tmp_path / "pending_requests.json",
        "completed": tmp_path / "completed_requests.json",
    }


def test_pending_request_survives_restart_and_can_still_be_approved(tmp_path):
    paths = _paths(tmp_path)

    # 사전 데이터(계좌·카드) 세팅 — 소유권 검증에 계좌가 필요함
    JsonAccountRepository(paths["accounts"]).save(
        Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000)
    )
    JsonCardRepository(paths["cards"]).save(
        Card(card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK)
    )

    # 1) 첫 번째 "프로세스" — 카드 분실정지를 제안(propose)만 하고 아직 승인은 안 받음
    orchestration, _ = _build_orchestration(paths)

    request = orchestration.propose(
        "card.block_as_lost", {"card_id": "c1"}, "u1", "thread-1", "req-1"
    )
    assert request.status is PendingStatus.PENDING

    # 2) 프로세스 재시작 시뮬레이션 — 전부 새 인스턴스로 다시 조립
    restarted_orchestration, restarted_card_repo = _build_orchestration(paths)

    # 재시작 후에도 대기 중이던 요청을 그대로 찾을 수 있어야 함(자동 실행은 안 됨)
    pending = restarted_orchestration.get_pending("thread-1")
    assert [p.request_id for p in pending] == ["req-1"]
    assert restarted_card_repo.find_by_id("c1").status is CardStatus.USABLE  # 아직 실행 안 됨

    # 3) 재시작 후 새로 받은 승인으로 실제 실행
    result = restarted_orchestration.approve("req-1")

    assert result.success is True
    assert restarted_card_repo.find_by_id("c1").status is CardStatus.LOST
    assert restarted_orchestration.get_pending("thread-1") == []
    assert restarted_orchestration.get_history("thread-1")[0].status is PendingStatus.EXECUTED


def test_completed_history_survives_restart(tmp_path):
    paths = _paths(tmp_path)

    JsonAccountRepository(paths["accounts"]).save(
        Account(account_id="a1", owner_id="u1", nickname="생활비", balance=1000)
    )
    JsonCardRepository(paths["cards"]).save(
        Card(card_id="c1", account_id="a1", name="생활비 카드", kind=CardKind.CHECK)
    )
    orchestration, _ = _build_orchestration(paths)

    orchestration.propose("card.block_as_lost", {"card_id": "c1"}, "u1", "thread-1", "req-1")
    orchestration.approve("req-1")

    restarted_orchestration, _ = _build_orchestration(paths)

    history = restarted_orchestration.get_history("thread-1")
    assert len(history) == 1
    assert history[0].request_id == "req-1"
    assert history[0].status is PendingStatus.EXECUTED
