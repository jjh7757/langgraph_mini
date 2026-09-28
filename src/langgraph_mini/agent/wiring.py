"""OrchestrationService를 실제 구현체(JSON 파일, 또는 Postgres/Redis)로 조립.

account/card/billing 테스트가 Memory 구현체로 직접 조립하듯, 여기서는 실행 시 실제로 쓸
리포지토리들로 조립한다. graph.py가 모듈을 불러올 때 이 함수를 한 번 호출해서 만든
OrchestrationService를 tool들에 물린다 — 테스트에서는 이 함수를 안 쓰고 Memory 구현체로
직접 조립한 OrchestrationService를 넣어서 검증한다(오케스트레이션 테스트와 같은 패턴).
"""

from pathlib import Path

import redis

from ..account.repository import AccountRepository
from ..account.repository_json import JsonAccountRepository
from ..account.repository_sql import SqlAccountRepository
from ..account.services.manage import DefaultAccountManageService
from ..account.services.query import DefaultAccountQueryService
from ..account.services.transfer import DefaultAccountTransferService
from ..account.transaction_repository_json import JsonTransactionRepository
from ..account.transaction_repository_sql import SqlTransactionRepository
from ..billing.repository_json import JsonBillRepository
from ..billing.repository_sql import SqlBillRepository
from ..billing.services.pay import DefaultBillPaymentService
from ..billing.services.query import DefaultBillingQueryService
from ..card.repository_json import JsonCardRepository
from ..card.repository_sql import SqlCardRepository
from ..card.reissue_request_repository_json import JsonReissueRequestRepository
from ..card.reissue_request_repository_sql import SqlReissueRequestRepository
from ..card.services.query import DefaultCardQueryService
from ..card.services.reissue import DefaultCardReissueService
from ..card.services.status import DefaultCardStatusService
from ..orchestration.actions import Repos, Services, build_actions
from ..orchestration.completed_repository_json import JsonCompletedRequestRepository
from ..orchestration.completed_repository_sql import SqlCompletedRequestRepository
from ..orchestration.pending_repository_json import JsonPendingRepository
from ..orchestration.pending_repository_redis import RedisPendingRepository
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


def build_orchestration_sql(redis_client: redis.Redis) -> OrchestrationService:
    """AWS 배포용 조립 — Postgres(Sql*Repository) + Redis(승인 대기 전용).

    build_orchestration()과 달리 커넥션 풀을 인자로 받지 않는다: Sql*Repository는 생성자
    없이 만들어지고 호출 시점에 db.postgres.current_connection()으로 "현재 요청의 트랜잭션"을
    찾아 쓰므로, 이 함수는 그래프와 함께 프로세스 시작 시 딱 한 번만 호출하면 된다 —
    api/app.py 참고. 왜 이렇게 나눴는지(그래프는 프로세스 전체에서 하나여야 InMemorySaver
    체크포인터가 대화 턴 사이에 유지되고, DB 쓰기는 요청 하나 단위로 트랜잭션이 걸려야 함)는
    db/postgres.py의 모듈 docstring 참고.
    """
    account_repo: AccountRepository = SqlAccountRepository()
    transaction_repo = SqlTransactionRepository()
    card_repo = SqlCardRepository()
    reissue_repo = SqlReissueRequestRepository()
    bill_repo = SqlBillRepository()

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

    pending_repo = RedisPendingRepository(redis_client)
    completed_repo = SqlCompletedRequestRepository()

    return OrchestrationService(actions, services, pending_repo, completed_repo)
