"""OrchestrationService를 실제 구현체(JSON 파일, 또는 Postgres/Redis)로 조립.

여기서는 실행 시 실제로 쓸 리포지토리(JSON 파일, 또는 Postgres/Redis)를 골라 assembly.py의
assemble_orchestration()에 넘길 뿐이다 — "서비스가 어떤 저장소를 필요로 하는가"는 그 함수 한 곳만
안다. 테스트와 평가(evals)도 같은 함수에 Memory 구현체를 넘겨 조립하므로, 배포와 테스트의 조립
방식이 어긋나지 않는다. 그래프가 이 함수를 프로세스 시작 시 한 번 호출해서 만든
OrchestrationService를 tool들에 물린다.
"""

from pathlib import Path

import redis

from ..account.repository_json import JsonAccountRepository
from ..account.repository_sql import SqlAccountRepository
from ..account.transaction_repository_json import JsonTransactionRepository
from ..account.transaction_repository_sql import SqlTransactionRepository
from ..billing.repository_json import JsonBillRepository
from ..billing.repository_sql import SqlBillRepository
from ..card.repository_json import JsonCardRepository
from ..card.repository_sql import SqlCardRepository
from ..card.reissue_request_repository_json import JsonReissueRequestRepository
from ..card.reissue_request_repository_sql import SqlReissueRequestRepository
from ..orchestration.completed_repository_json import JsonCompletedRequestRepository
from ..orchestration.completed_repository_sql import SqlCompletedRequestRepository
from ..orchestration.pending_repository_json import JsonPendingRepository
from ..orchestration.pending_repository_redis import RedisPendingRepository
from ..orchestration.service import OrchestrationService
from .assembly import assemble_orchestration


def build_orchestration(data_dir: str | Path = "data") -> OrchestrationService:
    data_dir = Path(data_dir)

    return assemble_orchestration(
        account_repo=JsonAccountRepository(data_dir / "accounts.json"),
        transaction_repo=JsonTransactionRepository(data_dir / "transactions.json"),
        card_repo=JsonCardRepository(data_dir / "cards.json"),
        reissue_repo=JsonReissueRequestRepository(data_dir / "reissue_requests.json"),
        bill_repo=JsonBillRepository(data_dir / "bills.json"),
        pending_repo=JsonPendingRepository(data_dir / "pending_requests.json"),
        completed_repo=JsonCompletedRequestRepository(data_dir / "completed_requests.json"),
    )


def build_orchestration_sql(redis_client: redis.Redis) -> OrchestrationService:
    """AWS 배포용 조립 — Postgres(Sql*Repository) + Redis(승인 대기 전용).

    build_orchestration()과 달리 커넥션 풀을 인자로 받지 않는다: Sql*Repository는 생성자
    없이 만들어지고 호출 시점에 db.postgres.current_connection()으로 "현재 요청의 트랜잭션"을
    찾아 쓰므로, 이 함수는 그래프와 함께 프로세스 시작 시 딱 한 번만 호출하면 된다 —
    api/app.py 참고. 왜 이렇게 나눴는지(그래프는 프로세스 전체에서 하나여야 InMemorySaver
    체크포인터가 대화 턴 사이에 유지되고, DB 쓰기는 요청 하나 단위로 트랜잭션이 걸려야 함)는
    db/postgres.py의 모듈 docstring 참고.
    """
    return assemble_orchestration(
        account_repo=SqlAccountRepository(),
        transaction_repo=SqlTransactionRepository(),
        card_repo=SqlCardRepository(),
        reissue_repo=SqlReissueRequestRepository(),
        bill_repo=SqlBillRepository(),
        pending_repo=RedisPendingRepository(redis_client),
        completed_repo=SqlCompletedRequestRepository(),
    )
