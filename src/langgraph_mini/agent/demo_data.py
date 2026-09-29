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

# 타인 계좌로도 이체할 수 있어야 해서 만든 "받는사람" 데모 계좌들 — 각자 별도 owner_id를
# 가진 남의 계좌라서(로그인 기능이 없어 실제로 그 사람이 되어볼 순 없음) 주 데모 사용자
# (DEMO_OWNER_ID)와는 독립적으로 존재 여부를 확인·생성한다. 그래서 이미 DEMO_OWNER_ID
# 데이터가 있는 기존 서버에 배포해도(주 데모 데이터 생성은 건너뛰지만) 이 목록은 그때
# 처음으로 새로 채워짐.
_RECIPIENT_ACCOUNTS = [
    ("demo-user-2", "demo-acc-3", "김철수", 300000),
    ("demo-user-3", "demo-acc-4", "이영희", 1200000),
]


def ensure_demo_data(
    account_repo: AccountRepository,
    card_repo: CardRepository,
    bill_repo: BillRepository,
    owner_id: str = DEMO_OWNER_ID,
) -> bool:
    """owner_id(주 데모 사용자) 데이터와 받는사람 데모 계좌들을 각각 독립적으로 확인해서
    없는 것만 만든다. 반환값은 "주 데모 사용자가 이번에 처음 생성됐는지"만 나타냄(호출한
    쪽이 "처음 실행" 안내를 띄울지 판단하는 데 씀) — 받는사람 계좌가 나중에 추가로
    생성돼도 이 반환값에는 안 잡힘(그 자체는 배너를 띄울 만한 "처음 실행"이 아니라서)."""
    created_primary = False
    if not account_repo.find_by_owner_id(owner_id):
        created_primary = True
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

    for recipient_owner_id, account_id, nickname, balance in _RECIPIENT_ACCOUNTS:
        existing = account_repo.find_by_owner_id(recipient_owner_id)
        if not existing:
            account_repo.save(
                Account(
                    account_id=account_id,
                    owner_id=recipient_owner_id,
                    nickname=nickname,
                    balance=balance,
                )
            )
        else:
            # 닉네임만 코드와 동기화(잔액은 실제 이체로 바뀔 수 있는 값이라 건드리지 않음) —
            # 이 목록의 이름을 나중에 바꾸면(예: 실존 인물 이름이라 바꾼 경우) 이미 데이터가
            # 있는 서버에도 다음 배포 때 자동으로 반영되게 하려는 목적.
            account = existing[0]
            if account.nickname != nickname:
                account.rename(nickname)
                account_repo.save(account)

    return created_primary
