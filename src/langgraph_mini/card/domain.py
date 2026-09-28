"""카드 서비스의 도메인 모델.

TODO(직접 구현): 표시된 메서드의 실제 로직. docstring은 지켜야 할 불변식/계약을 적어둔 것.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CardNotFoundError(Exception):
    """요청한 card_id의 Card가 존재하지 않을 때."""


class CardAlreadyLostError(Exception):
    """이미 LOST 상태인 카드를 다시 분실 정지하려 할 때."""


class CardNotUsableError(Exception):
    """USABLE 상태가 아닌 카드를 일시 잠금하려 할 때 (이미 LOCKED거나 LOST)."""


class CardNotLockedError(Exception):
    """LOCKED 상태가 아닌 카드의 잠금을 해제하려 할 때 (USABLE이거나 LOST).
    LOST 카드는 잠금 해제로 되돌릴 수 없음 — 재발급 절차를 거쳐야 함."""


class CardNotLostError(Exception):
    """LOST 상태가 아닌 카드를 재발급 신청하려 할 때."""


class ReissueRequestNotFoundError(Exception):
    """요청한 request_id의 ReissueRequest가 존재하지 않을 때."""


class ReissueRequestAlreadyExistsError(Exception):
    """같은 카드에 취소되지 않은(CANCELLED가 아닌) 재발급 신청이 이미 있을 때.
    args에 기존 ReissueRequest를 담아서 호출한 쪽이 안내 문구를 만들 수 있게 할 것."""


class ReissueRequestNotModifiableError(Exception):
    """RECEIVED 상태가 아닌(이미 제작 시작/완료/취소된) 신청을 수정·취소하려 할 때."""


class CardKind(Enum):
    CREDIT = "신용"
    CHECK = "체크"


class CardStatus(Enum):
    USABLE = "사용가능"
    LOCKED = "일시잠금"
    LOST = "분실정지"


@dataclass
class Card:
    """결제에 사용하는 카드. 하나의 출금 계좌(account_id)에 연결됨 — Account 자체는 모름,
    id로만 연결(account 패키지를 import하지 않음).

    status 전이는 이 클래스의 메서드(block_as_lost/lock_temporarily/unlock)를
    통해서만 이뤄져야 함(외부에서 status 필드 직접 대입 금지) — Account.balance와 같은 원칙.
    상태 전이는 계좌 잔액/거래내역에 영향을 주지 않음(분실정지·잠금·해제 전부).
    """

    card_id: str
    account_id: str  # 이 카드로 결제하면 출금되는 계좌
    name: str  # 표시용 카드 이름 (예: "국민 체크카드")
    kind: CardKind
    status: CardStatus = CardStatus.USABLE

    def block_as_lost(self) -> None:
        """USABLE 또는 LOCKED 상태에서만 가능 → LOST로 변경.
        이미 LOST면 CardAlreadyLostError."""
        ...

    def lock_temporarily(self) -> None:
        """USABLE 상태에서만 가능 → LOCKED로 변경.
        LOCKED 또는 LOST면 CardNotUsableError."""
        ...

    def unlock(self) -> None:
        """LOCKED 상태에서만 가능 → USABLE로 변경.
        USABLE 또는 LOST면 CardNotLockedError
        (LOST는 잠금 해제로 되돌릴 수 없음 — 재발급 절차를 거쳐야 함)."""
        ...


class DeliveryAddress(Enum):
    HOME = "집"
    WORK = "회사"


class ReissueStatus(Enum):
    RECEIVED = "접수"
    IN_PRODUCTION = "제작중"
    COMPLETED = "완료"
    CANCELLED = "취소"


@dataclass
class ReissueRequest:
    """분실 정지된 카드의 재발급 신청 한 건.

    status 전이는 이 클래스의 메서드를 통해서만 이뤄져야 함(직접 대입 금지).
    "카드 제작이 시작되기 전까지만" 수정·취소 가능 = status가 RECEIVED일 때만.
    IN_PRODUCTION/COMPLETED로의 전이는 이번 기능 범위 밖(별도 처리 필요 — 아직 없음).
    """

    request_id: str
    card_id: str
    delivery_address: DeliveryAddress
    status: ReissueStatus = ReissueStatus.RECEIVED
    created_at: datetime = field(default_factory=datetime.now)

    def change_delivery_address(self, new_address: DeliveryAddress) -> None:
        """RECEIVED 상태에서만 변경 가능.
        아니면 ReissueRequestNotModifiableError."""
        ...

    def cancel(self) -> None:
        """RECEIVED 상태에서만 취소 가능(status를 CANCELLED로 변경).
        아니면 ReissueRequestNotModifiableError."""
        ...
