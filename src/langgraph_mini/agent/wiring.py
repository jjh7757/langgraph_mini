"""OrchestrationService를 실제 구현체(JSON 파일)로 조립.

account/card/billing 테스트가 Memory 구현체로 직접 조립하듯, 여기서는 실행 시 실제로 쓸
JsonXRepository들로 조립한다. graph.py가 모듈을 불러올 때 이 함수를 한 번 호출해서 만든
OrchestrationService를 tool들에 물린다 — 테스트에서는 이 함수를 안 쓰고 Memory 구현체로
직접 조립한 OrchestrationService를 넣어서 검증한다(오케스트레이션 테스트와 같은 패턴).
"""

from pathlib import Path

from ..account.repository import AccountRepository
from ..account.repository_json import JsonAccountRepository
from ..account.services.manage import DefaultAccountManageService
from ..account.services.query import DefaultAccountQueryService
from ..account.services.transfer import DefaultAccountTransferService
from ..account.transaction_repository_json import JsonTransactionRepository
from ..billing.repository_json import JsonBillRepository
from ..billing.services.pay import DefaultBillPaymentService
from ..billing.services.query import DefaultBillingQueryService
from ..card.repository_json import JsonCardRepository
from ..card.reissue_request_repository_json import JsonReissueRequestRepository
from ..card.services.query import DefaultCardQueryService
from ..card.services.reissue import DefaultCardReissueService
from ..card.services.status import DefaultCardStatusService
from ..orchestration.actions import Repos, Services, build_actions
from ..orchestration.completed_repository_json import JsonCompletedRequestRepository
from ..orchestration.pending_repository_json import JsonPendingRepository
from ..orchestration.service import OrchestrationService


def build_orchestration(data_dir: str | Path = "data") -> OrchestrationService:
    data_dir = Path(data_dir)

    account_repo: AccountRepository = JsonAccountRepository(data_dir / "accounts.json")
    transaction_repo = JsonTransactionRepository(data_dir / "transactions.json")
    card_repo = JsonCardRepository(data_dir / "cards.json")
    reissue_repo = JsonReissueRequestRepository(data_dir / "reissue_requests.json")
    bill_repo = JsonBillRepository(data_dir / "bills.json")

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

    pending_repo = JsonPendingRepository(data_dir / "pending_requests.json")
    completed_repo = JsonCompletedRequestRepository(data_dir / "completed_requests.json")

    return OrchestrationService(actions, services, pending_repo, completed_repo)
