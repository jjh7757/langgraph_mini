"""액션 레지스트리 (generic dispatch).

Account/Card/Billing 합쳐서 실행형·조회형 액션이 20개가 넘어서, 액션마다 propose_x/
approve_x 메서드 쌍을 만드는 대신 "action 이름 문자열 + params dict"로 범용 디스패치한다.
OrchestrationService.query()/propose()가 전부 이 하나의 테이블을 봄 — 조회형/실행형을
가르는 건 테이블이 아니라 OrchestrationService 쪽 메서드 선택(조회는 즉시 실행,
실행형은 propose 후 approve).
"""

from dataclasses import dataclass
from typing import Any, Callable

from ..account.repository import AccountRepository
from ..account.services.manage import AccountManageService
from ..account.services.query import AccountQueryService
from ..account.services.transfer import AccountTransferService
from ..billing.repository import BillRepository
from ..billing.services.pay import BillPaymentService
from ..billing.services.query import BillingQueryService
from ..card.reissue_request_repository import ReissueRequestRepository
from ..card.repository import CardRepository
from ..card.services.query import CardQueryService
from ..card.services.reissue import CardReissueService
from ..card.services.status import CardStatusService
from . import ownership as own


@dataclass
class Services:
    """실행에 실제로 쓰는 도메인 서비스들. Orchestration은 이 protocol들만 알고
    구현체(Default...)는 생성자로 주입받는 쪽(agent/wiring)이 조립해서 넘겨줌."""

    account_query: AccountQueryService
    account_transfer: AccountTransferService
    account_manage: AccountManageService
    card_query: CardQueryService
    card_status: CardStatusService
    card_reissue: CardReissueService
    billing_query: BillingQueryService
    billing_payment: BillPaymentService


@dataclass
class Repos:
    """소유권 검증에만 쓰는 저장소들. Services 내부의 Default*Service들도 결국 같은
    repo를 들고 있지만, 소유권 검증은 도메인 서비스가 모르는(Orchestration만의) 책임이라
    따로 주입받음."""

    account: AccountRepository
    card: CardRepository
    reissue_request: ReissueRequestRepository
    bill: BillRepository


@dataclass
class ActionSpec:
    required_params: list[str]
    verify_owner: Callable[[dict, str], None]  # (params, requester_id) -> None, 실패 시 NotOwnerError
    execute: Callable[[dict, Services], Any]  # (params, services) -> 실행 결과


def build_actions(repos: Repos) -> dict[str, ActionSpec]:
    """repos를 클로저로 바인딩해서 ACTIONS 딕셔너리를 조립.
    Services는 execute 시그니처에 남겨둠 — 매 호출마다 OrchestrationService가 들고
    있는 같은 인스턴스를 그대로 넘겨주면 되므로 여기서 미리 바인딩할 필요 없음."""

    return {
        # ── account: 실행형 ──────────────────────────────────────────
        "account.rename": ActionSpec(
            required_params=["account_id", "new_nickname"],
            verify_owner=lambda p, rid: own.verify_account_owner(repos.account, p["account_id"], rid),
            execute=lambda p, services: services.account_manage.rename_account(
                p["account_id"], p["new_nickname"]
            ),
        ),
        "account.transfer": ActionSpec(
            required_params=["from_id", "to_id", "amount"],
            verify_owner=lambda p, rid: own.verify_account_owner(repos.account, p["from_id"], rid),
            execute=lambda p, services: services.account_transfer.transfer(
                p["from_id"], p["to_id"], p["amount"]
            ),
        ),
        "account.confirm_conditional_transfer": ActionSpec(
            required_params=["quote"],
            verify_owner=lambda p, rid: own.verify_account_owner(repos.account, p["quote"].from_id, rid),
            execute=lambda p, services: services.account_transfer.confirm_conditional_transfer(
                p["quote"]
            ),
        ),
        "account.transfer_split": ActionSpec(
            required_params=["from_id", "targets"],
            verify_owner=lambda p, rid: own.verify_account_owner(repos.account, p["from_id"], rid),
            execute=lambda p, services: services.account_transfer.transfer_split(
                p["from_id"], p["targets"]
            ),
        ),
        # ── account: 조회형 ──────────────────────────────────────────
        "account.get_account": ActionSpec(
            required_params=["account_id"],
            verify_owner=lambda p, rid: own.verify_account_owner(repos.account, p["account_id"], rid),
            execute=lambda p, services: services.account_query.get_account(p["account_id"]),
        ),
        "account.get_accounts": ActionSpec(
            required_params=["owner_id"],
            verify_owner=lambda p, rid: own.verify_is_self(p["owner_id"], rid),
            execute=lambda p, services: services.account_query.get_accounts(p["owner_id"]),
        ),
        "account.get_total_balance": ActionSpec(
            required_params=["owner_id"],
            verify_owner=lambda p, rid: own.verify_is_self(p["owner_id"], rid),
            execute=lambda p, services: services.account_query.get_total_balance(p["owner_id"]),
        ),
        "account.get_transactions": ActionSpec(
            required_params=["account_id"],
            verify_owner=lambda p, rid: own.verify_account_owner(repos.account, p["account_id"], rid),
            execute=lambda p, services: services.account_query.get_transactions(
                p["account_id"], p.get("filter")
            ),
        ),
        "account.calculate_conditional_transfer": ActionSpec(
            required_params=["from_id", "to_id", "condition"],
            verify_owner=lambda p, rid: own.verify_account_owner(repos.account, p["from_id"], rid),
            execute=lambda p, services: services.account_transfer.calculate_conditional_transfer(
                p["from_id"], p["to_id"], p["condition"]
            ),
        ),
        # ── card: 실행형 ──────────────────────────────────────────
        "card.block_as_lost": ActionSpec(
            required_params=["card_id"],
            verify_owner=lambda p, rid: own.verify_card_owner(repos.card, repos.account, p["card_id"], rid),
            execute=lambda p, services: services.card_status.block_as_lost(p["card_id"]),
        ),
        "card.lock_temporarily": ActionSpec(
            required_params=["card_id"],
            verify_owner=lambda p, rid: own.verify_card_owner(repos.card, repos.account, p["card_id"], rid),
            execute=lambda p, services: services.card_status.lock_temporarily(p["card_id"]),
        ),
        "card.unlock": ActionSpec(
            required_params=["card_id"],
            verify_owner=lambda p, rid: own.verify_card_owner(repos.card, repos.account, p["card_id"], rid),
            execute=lambda p, services: services.card_status.unlock(p["card_id"]),
        ),
        "card.request_reissue": ActionSpec(
            required_params=["card_id", "delivery_address", "request_id"],
            verify_owner=lambda p, rid: own.verify_card_owner(repos.card, repos.account, p["card_id"], rid),
            execute=lambda p, services: services.card_reissue.request_reissue(
                p["card_id"], p["delivery_address"], p["request_id"]
            ),
        ),
        "card.change_delivery_address": ActionSpec(
            required_params=["request_id", "new_address"],
            verify_owner=lambda p, rid: own.verify_reissue_request_owner(
                repos.reissue_request, repos.card, repos.account, p["request_id"], rid
            ),
            execute=lambda p, services: services.card_reissue.change_delivery_address(
                p["request_id"], p["new_address"]
            ),
        ),
        "card.cancel_reissue_request": ActionSpec(
            required_params=["request_id"],
            verify_owner=lambda p, rid: own.verify_reissue_request_owner(
                repos.reissue_request, repos.card, repos.account, p["request_id"], rid
            ),
            execute=lambda p, services: services.card_reissue.cancel_reissue_request(p["request_id"]),
        ),
        # ── card: 조회형 ──────────────────────────────────────────
        "card.get_card": ActionSpec(
            required_params=["card_id"],
            verify_owner=lambda p, rid: own.verify_card_owner(repos.card, repos.account, p["card_id"], rid),
            execute=lambda p, services: services.card_query.get_card(p["card_id"]),
        ),
        "card.get_cards": ActionSpec(
            required_params=["owner_id"],
            verify_owner=lambda p, rid: own.verify_is_self(p["owner_id"], rid),
            execute=lambda p, services: services.card_query.get_cards(p["owner_id"]),
        ),
        "card.get_reissue_request": ActionSpec(
            required_params=["request_id"],
            verify_owner=lambda p, rid: own.verify_reissue_request_owner(
                repos.reissue_request, repos.card, repos.account, p["request_id"], rid
            ),
            execute=lambda p, services: services.card_reissue.get_reissue_request(p["request_id"]),
        ),
        "card.get_reissue_requests_by_card": ActionSpec(
            required_params=["card_id"],
            verify_owner=lambda p, rid: own.verify_card_owner(repos.card, repos.account, p["card_id"], rid),
            execute=lambda p, services: services.card_reissue.get_reissue_requests_by_card(
                p["card_id"]
            ),
        ),
        # ── billing: 실행형 ──────────────────────────────────────────
        "billing.pay_bill": ActionSpec(
            required_params=["bill_id", "account_id"],
            verify_owner=lambda p, rid: (
                own.verify_bill_owner(repos.bill, p["bill_id"], rid),
                own.verify_account_owner(repos.account, p["account_id"], rid),
            ),
            execute=lambda p, services: services.billing_payment.pay_bill(
                p["bill_id"], p["account_id"]
            ),
        ),
        "billing.pay_bills": ActionSpec(
            required_params=["account_id", "bill_ids"],
            verify_owner=lambda p, rid: (
                own.verify_account_owner(repos.account, p["account_id"], rid),
                [own.verify_bill_owner(repos.bill, bill_id, rid) for bill_id in p["bill_ids"]],
            ),
            execute=lambda p, services: services.billing_payment.pay_bills(
                p["account_id"], p["bill_ids"]
            ),
        ),
        # ── billing: 조회형 ──────────────────────────────────────────
        "billing.get_unpaid_bills": ActionSpec(
            required_params=["owner_id"],
            verify_owner=lambda p, rid: own.verify_is_self(p["owner_id"], rid),
            execute=lambda p, services: services.billing_query.get_unpaid_bills(p["owner_id"]),
        ),
    }
