"""저장소 7개를 받아 OrchestrationService를 만드는 유일한 조립 지점.

"서비스가 어떤 저장소를 필요로 하는가"를 아는 곳은 여기 하나뿐이다. 호출하는 쪽(wiring.py의 JSON/SQL
조립, 테스트, 평가 하네스)은 어떤 종류의 저장소(Memory/JSON/Postgres·Redis)를 쓸지만 정해서 넘긴다.
서비스에 의존성이 늘거나 새 서비스가 생기면 이 파일 한 곳만 고치면 된다.

wiring.py와 나눈 이유: wiring.py는 redis와 SQL 구현체까지 임포트하는데, 테스트와 평가는 그것들이
필요 없다 — 이 모듈은 Protocol 기반이라 어떤 저장소 구현체도 임포트하지 않는다.
인자를 키워드 전용으로 둔 이유: 저장소 7개가 모양이 비슷해서 위치 인자로 받으면 순서를 바꿔 넣어도
타입 검사기가 못 잡는다.
"""

from ..account.repository import AccountRepository
from ..account.services.manage import DefaultAccountManageService
from ..account.services.query import DefaultAccountQueryService
from ..account.services.transfer import DefaultAccountTransferService
from ..account.transaction_repository import TransactionRepository
from ..billing.repository import BillRepository
from ..billing.services.pay import DefaultBillPaymentService
from ..billing.services.query import DefaultBillingQueryService
from ..card.reissue_request_repository import ReissueRequestRepository
from ..card.repository import CardRepository
from ..card.services.query import DefaultCardQueryService
from ..card.services.reissue import DefaultCardReissueService
from ..card.services.status import DefaultCardStatusService
from ..orchestration.actions import Repos, Services, build_actions
from ..orchestration.completed_repository import CompletedRequestRepository
from ..orchestration.pending_repository import PendingRepository
from ..orchestration.service import OrchestrationService


def assemble_orchestration(
    *,
    account_repo: AccountRepository,
    transaction_repo: TransactionRepository,
    card_repo: CardRepository,
    reissue_repo: ReissueRequestRepository,
    bill_repo: BillRepository,
    pending_repo: PendingRepository,
    completed_repo: CompletedRequestRepository,
) -> OrchestrationService:
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
    return OrchestrationService(build_actions(repos), services, pending_repo, completed_repo)
