"""계좌 이체 서비스의 도메인 모델.

TODO(직접 구현): 표시된 메서드의 실제 로직. docstring은 지켜야 할 불변식/계약을 적어둔 것.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class AccountNotFoundError(Exception):
    """요청한 account_id의 Account가 존재하지 않을 때."""


class InsufficientBalanceError(Exception):
    """잔액보다 큰 금액을 출금하려 할 때."""


class DuplicateNicknameError(Exception):
    """같은 소유자(owner_id)의 다른 계좌와 별명이 중복될 때."""


class CardNotFoundError(Exception):
    """요청한 card_id의 Card가 존재하지 않을 때."""


@dataclass
class Account:
    account_id: str
    owner_id: str
    nickname: str
    balance: int  # 원 단위 정수. float 금지(반올림 오차 발생)

    def withdraw(self, amount: int) -> None:
        """balance -= amount.

        불변식: 출금 후 balance는 절대 음수가 될 수 없다.
        위반 시 InsufficientBalanceError를 발생시킬 것.
        balance 필드는 이 메서드를 통해서만 바뀌어야 한다(외부에서 직접 대입 금지).
        """
        if amount <= 0:
            raise ValueError("withdraw amount must be positive")
        if amount > self.balance:
            raise InsufficientBalanceError
        else:
            self.balance -= amount

    def deposit(self, amount: int) -> None:
        """balance += amount."""
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        self.balance += amount

    def rename(self, new_nickname: str) -> None:
        """nickname을 new_nickname으로 변경.

        불변식(이 메서드 안에서 검증): 앞뒤 공백 제거 후 길이가 1~20자.
        다른 계좌와의 중복 여부는 이 메서드가 알 수 없음(다른 Account를 모름) —
        그건 서비스 계층(AccountManageService)이 AccountRepository로 확인해야 함.
        """
        new_nickname = new_nickname.strip()
        if not (1 <= len(new_nickname) <= 20):
            raise ValueError("nickname length must be between 1 and 20")
        self.nickname = new_nickname


class TransactionType(Enum):
    TRANSFER_OUT = "이체출금"
    TRANSFER_IN = "이체입금"
    CARD_PAYMENT = "카드결제"


@dataclass
class Transaction:
    """거래 내역 한 줄. 이체는 계좌당 한 건씩(양쪽) 생성됨 — 예: A->B 이체 시
    A 계좌엔 TRANSFER_OUT, B 계좌엔 TRANSFER_IN 두 건이 각각 만들어짐.
    "이번 달 생활비 출금 내역" 같은 계좌 단위 조회를 하려면 이렇게 계좌별로
    갈라서 저장해야 함.
    """

    account_id: str
    transaction_type: TransactionType
    amount: int
    counterpart_id: str | None = None  # 이체 상대 계좌 id (카드결제면 None)
    card_id: str | None = None  # 카드결제일 때 사용한 카드 (아니면 None)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TransactionFilter:
    """거래 내역 조회 필터. 전부 선택 사항이며 None이면 그 조건은 적용 안 함.

    start_date/end_date는 포함(inclusive) 범위.
    "이번 달"/"이번 주" 같은 자연어를 실제 날짜로 바꾸는 건 이 서비스의 책임이 아님
    (호출하는 쪽에서 이미 계산된 날짜를 넘겨줌).
    """

    start_date: date | None = None
    end_date: date | None = None
    min_amount: int | None = None
    max_amount: int | None = None
    transaction_type: TransactionType | None = None


@dataclass
class Card:
    """결제에 사용하는 카드. 하나의 출금 계좌에 연결됨."""

    card_id: str
    account_id: str  # 이 카드로 결제하면 출금되는 계좌
    name: str  # 표시용 카드 이름 (예: "국민 체크카드")


@dataclass
class TransferCondition:
    """조건부 이체 조건: 출금 계좌에 남길 금액.

    이체액 = 출금 계좌 현재 잔액 - remaining_balance (서비스 계층에서 계산).
    """

    remaining_balance: int  # 0 이상 정수
