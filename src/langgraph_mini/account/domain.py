"""계좌 이체 서비스의 도메인 모델.

TODO(직접 구현): 각 메서드의 실제 로직. 아래 docstring은 지켜야 할 불변식/계약을 적어둔 것.
"""

from dataclasses import dataclass, field
from datetime import datetime



class AccountNotFoundError(Exception):
    """요청한 id의 Account가 존재하지 않을 때."""


class InsufficientBalanceError(Exception):
    """잔액보다 큰 금액을 출금하려 할 때."""


@dataclass
class Account:
    id: str
    alias: str
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

    def rename(self, new_alias: str) -> None:
        """alias를 new_alias로 변경."""
        new_alias = new_alias.strip()
        if not new_alias:
            raise ValueError("alias must not be empty")
        self.alias = new_alias


@dataclass
class Transaction:
    from_id: str
    to_id: str
    amount: int
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TransferCondition:
    """TODO(결정 필요): 조건부 이체(transfer_conditional)의 실제 조건.

    잔액 기준인지, 예약 시각 기준인지 등을 먼저 정하고 필드를 채울 것.
    설계초안/구현_가이드라인.md 5절 참고.
    """
