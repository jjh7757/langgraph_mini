"""리소스 종류별 소유권 검증 함수.

리소스마다 owner_id까지 가는 경로가 다름:
    Account/Bill  — owner_id를 직접 가짐
    Card          — account_id로 Account를 거쳐야 함 (2단계)
    ReissueRequest — card_id로 Card를, 그 card로 Account를 거쳐야 함 (3단계)

리소스 자체가 없으면(AccountNotFoundError 등) 그대로 위로 전파함 — 이미 구조화된
도메인 예외라 여기서 새로 감쌀 필요 없음.
"""

from ..account.repository import AccountRepository
from ..billing.repository import BillRepository
from ..card.reissue_request_repository import ReissueRequestRepository
from ..card.repository import CardRepository
from .domain import NotOwnerError


def verify_account_owner(account_repo: AccountRepository, account_id: str, requester_id: str) -> None:
    account = account_repo.find_by_id(account_id)
    if account.owner_id != requester_id:
        raise NotOwnerError(account_id)


def verify_card_owner(
    card_repo: CardRepository, account_repo: AccountRepository, card_id: str, requester_id: str
) -> None:
    card = card_repo.find_by_id(card_id)
    verify_account_owner(account_repo, card.account_id, requester_id)


def verify_reissue_request_owner(
    reissue_repo: ReissueRequestRepository,
    card_repo: CardRepository,
    account_repo: AccountRepository,
    request_id: str,
    requester_id: str,
) -> None:
    request = reissue_repo.find_by_id(request_id)
    verify_card_owner(card_repo, account_repo, request.card_id, requester_id)


def verify_bill_owner(bill_repo: BillRepository, bill_id: str, requester_id: str) -> None:
    bill = bill_repo.find_by_id(bill_id)
    if bill.owner_id != requester_id:
        raise NotOwnerError(bill_id)


def verify_is_self(owner_id: str, requester_id: str) -> None:
    """owner_id 자체를 params로 받는 조회(get_accounts 등) — 남의 목록을 볼 수 없게."""
    if owner_id != requester_id:
        raise NotOwnerError(owner_id)
