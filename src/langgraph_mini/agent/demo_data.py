"""데모용 계좌·카드·청구서 생성 — CLI(JSON)와 API(Postgres) 둘 다 이 로직을 공유한다.

이 프로젝트엔 계좌/카드/청구서를 "만드는" 기능이 없어서(기존 데이터를 다루는 기능만 있음),
빈 저장소로 처음 실행하면 가지고 놀 데이터가 없다 — owner_id 기준으로 없으면 한 번만
만들어둔다(idempotent).
"""

from datetime import date, timedelta

from ..account.domain import Account
from ..account.repository import AccountRepository
from ..billing.domain import Bill
from ..billing.repository import BillRepository
from ..card.domain import Card, CardKind
from ..card.repository import CardRepository

DEMO_OWNER_ID = "demo-user"


def ensure_demo_data(
    account_repo: AccountRepository,
    card_repo: CardRepository,
    bill_repo: BillRepository,
    owner_id: str = DEMO_OWNER_ID,
) -> bool:
    """이미 owner_id의 계좌가 있으면 아무것도 안 하고 False를 반환.
    처음이면 데모 데이터를 만들고 True(호출한 쪽이 "처음 실행" 안내를 띄울지 판단하는 데 씀)."""
    if account_repo.find_by_owner_id(owner_id):
        return False

    account_repo.save(
        Account(account_id="demo-acc-1", owner_id=owner_id, nickname="생활비", balance=500000)
    )
    account_repo.save(
        Account(account_id="demo-acc-2", owner_id=owner_id, nickname="저축", balance=2000000)
    )
    card_repo.save(
        Card(
            card_id="demo-card-1",
            account_id="demo-acc-1",
            name="생활비 체크카드",
            kind=CardKind.CHECK,
        )
    )
    bill_repo.save(
        Bill(
            bill_id="demo-bill-1",
            owner_id=owner_id,
            name="전기요금",
            amount=45000,
            due_date=date.today() + timedelta(days=10),
        )
    )
    return True
