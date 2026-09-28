"""Orchestration Service의 도메인 모델."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PendingStatus(Enum):
    PENDING = "대기"
    REJECTED = "거절됨"
    EXECUTED = "완료"
    FAILED = "실패"  # execute가 도메인 예외를 던진 경우


@dataclass
class ActionResult:
    """예외 → 구조화 변환 결과. approve()가 도메인 예외를 그대로 올리지 않고 여기 담아 반환."""

    success: bool
    value: Any = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class PendingRequest:
    """승인 대기(또는 이미 종결된) 요청 한 건.

    status 전이는 OrchestrationService(propose/revise/approve/reject)를 통해서만
    이뤄져야 함 — Account.balance/Card.status와 같은 원칙.
    """

    request_id: str  # 멱등성 키
    thread_id: str  # 대화 스레드 — 복구/자연어 승인/후속 조회 전부 이걸로 찾음
    requester_id: str
    action: str  # actions.ACTIONS의 key
    params: dict
    status: PendingStatus = PendingStatus.PENDING
    result: ActionResult | None = None  # 종결(EXECUTED/FAILED/REJECTED) 후 채워짐
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: datetime | None = None


class NotOwnerError(Exception):
    """요청자가 대상 리소스의 소유자가 아닐 때."""


class ActionNotRegisteredError(Exception):
    """ACTIONS에 없는 action 이름일 때."""


class MissingParamsError(Exception):
    """params에 필수 필드가 빠졌을 때. args = (action, 빠진 필드 목록)."""


class PendingRequestNotFoundError(Exception):
    """request_id에 해당하는 PendingRequest가 없을 때."""


class PendingRequestNotPendingError(Exception):
    """이미 처리(승인/거절/완료)된 요청을 다시 approve/reject/revise하려 할 때."""
