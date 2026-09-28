"""청구(Billing) 서비스의 도메인 모델."""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class BillNotFoundError(Exception):
    """요청한 bill_id의 Bill이 존재하지 않을 때."""


class BillAlreadyPaidError(Exception):
    """이미 PAID 상태인 청구서를 다시 납부하려 할 때."""


class BillStatus(Enum):
    UNPAID = "미납"
    PAID = "납부완료"


@dataclass
class Bill:
    """청구서 한 건. 특정 계좌에 미리 묶여있지 않음 — 납부 시점에 출금 계좌를 고름.

    status 전이는 pay()를 통해서만 이뤄져야 함(외부에서 직접 대입 금지) —
    Account.balance/Card.status와 같은 원칙.
    기한(due_date)이 지나도 연체료 없이 그대로 납부 가능 — pay()는 due_date를 검사하지 않음.
    """

    bill_id: str
    owner_id: str  # 청구 대상
    name: str  # 예: "전기요금"
    amount: int
    due_date: date
    status: BillStatus = BillStatus.UNPAID

    def pay(self) -> None:
        """UNPAID 상태에서만 가능 → PAID로 변경. 이미 PAID면 BillAlreadyPaidError."""
        if self.status is BillStatus.PAID:
            raise BillAlreadyPaidError(self.bill_id)
        self.status = BillStatus.PAID
