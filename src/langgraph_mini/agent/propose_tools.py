"""LLM에게 노출하는 Tool 22개 (실행형 12 + 조회형 10) — orchestration/actions.py의
ACTIONS(23개) 중 챗봇에 노출할 22개와 대응한다(`account.list_recipients`는 REST API
전용 조회라 tool로는 안 둠 — 웹 UI의 "받는사람 목록"에서만 씀). 실행형은
propose_and_confirm(승인 루프)을 거치고, 조회형은 orchestration.query()로 바로 실행한다.

`build_tools(orchestration, confirmation_llm)`이 팩토리 — 모듈 임포트 시점에 실제
OrchestrationService를 만들지 않고, 호출하는 쪽(graph.py 또는 테스트)이 원하는
orchestration/llm으로 tool들을 조립한다(account/card/billing의 Default*Service가
생성자로 repo를 주입받는 것과 같은 이유 — 테스트에서 Memory 구현체를 넣을 수 있게).
"""

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from pydantic import BaseModel

from ..account.domain import TransactionFilter, TransactionType, TransferCondition
from ..card.domain import DeliveryAddress
from ..orchestration.domain import ActionResult
from ..orchestration.service import OrchestrationService
from .confirmation import propose_and_confirm
from .context import get_context


class TransferTarget(BaseModel):
    account_id: str
    amount: int


def _to_plain(value):
    """dataclass/Enum/date/datetime을 LLM이 읽기 좋은 순수 dict/list/primitive로 변환.

    json_codec.encode()와 달리 타입 태그(__dataclass__ 등)를 안 남김 — 이건 되돌릴
    필요 없는 "보여주기 전용" 변환이라 최대한 깔끔한 형태가 우선.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


def _format_value(value) -> str:
    return json.dumps(_to_plain(value), ensure_ascii=False)


def _format_result(result: ActionResult) -> str:
    if result.success:
        return f"완료: {_format_value(result.value)}"
    return f"실패({result.error_type}): {result.error_message}"


def build_tools(orchestration: OrchestrationService, confirmation_llm) -> list:
    def _propose(action: str, params: dict, tool_call_id: str, config: RunnableConfig) -> str:
        ctx = get_context(config)
        result = propose_and_confirm(
            action, params, ctx, tool_call_id, orchestration, confirmation_llm
        )
        return _format_result(result)

    def _query(action: str, params: dict, config: RunnableConfig) -> str:
        ctx = get_context(config)
        value = orchestration.query(action, params, ctx.requester_id)
        return _format_value(value)

    # ── 실행형 12개 ──────────────────────────────────────────────

    @tool
    def rename_account(
        account_id: str,
        new_nickname: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """계좌 별명을 바꿉니다. 실행 전 사용자 승인이 필요합니다."""
        return _propose(
            "account.rename",
            {"account_id": account_id, "new_nickname": new_nickname},
            tool_call_id,
            config,
        )

    @tool
    def transfer_money(
        from_id: str,
        to_id: str,
        amount: int,
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """한 계좌에서 다른 계좌로 정해진 금액을 이체합니다. 실행 전 사용자 승인이 필요합니다."""
        return _propose(
            "account.transfer",
            {"from_id": from_id, "to_id": to_id, "amount": amount},
            tool_call_id,
            config,
        )

    @tool
    def confirm_conditional_transfer(
        from_id: str,
        to_id: str,
        remaining_balance: int,
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """출금 계좌에 remaining_balance만 남기고 나머지 전부를 이체합니다(조건부 이체 실행).
        실행 전 사용자 승인이 필요합니다. 이체액은 이 tool이 실행 시점에 다시 계산합니다."""
        ctx = get_context(config)
        condition = TransferCondition(remaining_balance=remaining_balance)
        quote = orchestration.query(
            "account.calculate_conditional_transfer",
            {"from_id": from_id, "to_id": to_id, "condition": condition},
            ctx.requester_id,
        )
        return _propose(
            "account.confirm_conditional_transfer", {"quote": quote}, tool_call_id, config
        )

    @tool
    def transfer_split(
        from_id: str,
        targets: list[TransferTarget],
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """한 계좌에서 여러 계좌로 나눠 이체합니다. 실행 전 사용자 승인이 필요합니다."""
        tuples = [(t.account_id, t.amount) for t in targets]
        return _propose(
            "account.transfer_split", {"from_id": from_id, "targets": tuples}, tool_call_id, config
        )

    @tool
    def block_card_as_lost(
        card_id: str, tool_call_id: Annotated[str, InjectedToolCallId], config: RunnableConfig
    ) -> str:
        """카드를 분실 정지합니다. 실행 전 사용자 승인이 필요합니다."""
        return _propose("card.block_as_lost", {"card_id": card_id}, tool_call_id, config)

    @tool
    def lock_card_temporarily(
        card_id: str, tool_call_id: Annotated[str, InjectedToolCallId], config: RunnableConfig
    ) -> str:
        """카드를 일시 잠금합니다(분실 정지와 다름 — 나중에 잠금 해제 가능).
        실행 전 사용자 승인이 필요합니다."""
        return _propose("card.lock_temporarily", {"card_id": card_id}, tool_call_id, config)

    @tool
    def unlock_card(
        card_id: str, tool_call_id: Annotated[str, InjectedToolCallId], config: RunnableConfig
    ) -> str:
        """일시 잠긴 카드를 잠금 해제합니다(분실 정지된 카드는 해제할 수 없음).
        실행 전 사용자 승인이 필요합니다."""
        return _propose("card.unlock", {"card_id": card_id}, tool_call_id, config)

    @tool
    def request_card_reissue(
        card_id: str,
        delivery_address: Literal["집", "회사"],
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """분실 정지된 카드의 재발급을 신청합니다. 배송지는 집 또는 회사 중 하나입니다.
        실행 전 사용자 승인이 필요합니다."""
        return _propose(
            "card.request_reissue",
            {
                "card_id": card_id,
                "delivery_address": DeliveryAddress(delivery_address),
                "request_id": tool_call_id,
            },
            tool_call_id,
            config,
        )

    @tool
    def change_reissue_delivery_address(
        reissue_request_id: str,
        new_address: Literal["집", "회사"],
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """접수된 재발급 신청의 배송지를 바꿉니다(카드 제작이 시작되기 전까지만 가능).
        실행 전 사용자 승인이 필요합니다."""
        return _propose(
            "card.change_delivery_address",
            {"request_id": reissue_request_id, "new_address": DeliveryAddress(new_address)},
            tool_call_id,
            config,
        )

    @tool
    def cancel_card_reissue_request(
        reissue_request_id: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """접수된 재발급 신청을 취소합니다(카드 제작이 시작되기 전까지만 가능).
        실행 전 사용자 승인이 필요합니다."""
        return _propose(
            "card.cancel_reissue_request", {"request_id": reissue_request_id}, tool_call_id, config
        )

    @tool
    def pay_bill(
        bill_id: str,
        account_id: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """청구서 한 건을 지정한 계좌에서 전액 납부합니다. 기한이 지났어도 연체료 없이
        납부됩니다. 실행 전 사용자 승인이 필요합니다."""
        return _propose(
            "billing.pay_bill", {"bill_id": bill_id, "account_id": account_id}, tool_call_id, config
        )

    @tool
    def pay_bills(
        account_id: str,
        bill_ids: list[str],
        tool_call_id: Annotated[str, InjectedToolCallId],
        config: RunnableConfig,
    ) -> str:
        """여러 청구서를 한 계좌에서 일괄 납부합니다(납기일이 빠른 청구서부터 처리하고,
        잔액이 부족한 건은 건너뛰고 계속 진행합니다). 실행 전 사용자 승인이 필요합니다."""
        return _propose(
            "billing.pay_bills", {"account_id": account_id, "bill_ids": bill_ids}, tool_call_id, config
        )

    # ── 조회형 10개 ──────────────────────────────────────────────

    @tool
    def calculate_conditional_transfer(
        from_id: str, to_id: str, remaining_balance: int, config: RunnableConfig
    ) -> str:
        """출금 계좌에 remaining_balance만 남기고 이체하면 이체액이 얼마가 되는지
        미리 계산만 해서 보여줍니다(승인/실행 없음 — 실제 이체는
        confirm_conditional_transfer를 부르세요)."""
        condition = TransferCondition(remaining_balance=remaining_balance)
        return _query(
            "account.calculate_conditional_transfer",
            {"from_id": from_id, "to_id": to_id, "condition": condition},
            config,
        )

    @tool
    def get_account(account_id: str, config: RunnableConfig) -> str:
        """계좌 정보(별명·잔액 등)를 조회합니다."""
        return _query("account.get_account", {"account_id": account_id}, config)

    @tool
    def get_my_accounts(config: RunnableConfig) -> str:
        """내 계좌 목록을 조회합니다."""
        ctx = get_context(config)
        return _query("account.get_accounts", {"owner_id": ctx.requester_id}, config)

    @tool
    def get_my_total_balance(config: RunnableConfig) -> str:
        """내 모든 계좌의 잔액 합계를 조회합니다."""
        ctx = get_context(config)
        return _query("account.get_total_balance", {"owner_id": ctx.requester_id}, config)

    @tool
    def get_transactions(
        account_id: str,
        config: RunnableConfig,
        start_date: str | None = None,
        end_date: str | None = None,
        min_amount: int | None = None,
        max_amount: int | None = None,
        transaction_type: Literal["이체출금", "이체입금", "카드결제", "청구서납부"] | None = None,
    ) -> str:
        """계좌의 거래 내역을 조회합니다. 필터는 전부 선택 사항입니다(날짜는 YYYY-MM-DD)."""
        filter_ = None
        if any([start_date, end_date, min_amount, max_amount, transaction_type]):
            filter_ = TransactionFilter(
                start_date=date.fromisoformat(start_date) if start_date else None,
                end_date=date.fromisoformat(end_date) if end_date else None,
                min_amount=min_amount,
                max_amount=max_amount,
                transaction_type=TransactionType(transaction_type) if transaction_type else None,
            )
        return _query(
            "account.get_transactions", {"account_id": account_id, "filter": filter_}, config
        )

    @tool
    def get_card(card_id: str, config: RunnableConfig) -> str:
        """카드 정보(이름·종류·상태)를 조회합니다."""
        return _query("card.get_card", {"card_id": card_id}, config)

    @tool
    def get_my_cards(config: RunnableConfig) -> str:
        """내 카드 목록과 각 카드의 상태를 조회합니다."""
        ctx = get_context(config)
        return _query("card.get_cards", {"owner_id": ctx.requester_id}, config)

    @tool
    def get_reissue_request(reissue_request_id: str, config: RunnableConfig) -> str:
        """재발급 신청 한 건의 배송지·처리 상태를 조회합니다."""
        return _query("card.get_reissue_request", {"request_id": reissue_request_id}, config)

    @tool
    def get_reissue_requests_by_card(card_id: str, config: RunnableConfig) -> str:
        """특정 카드의 재발급 신청 내역을 전부 조회합니다."""
        return _query("card.get_reissue_requests_by_card", {"card_id": card_id}, config)

    @tool
    def get_my_unpaid_bills(config: RunnableConfig) -> str:
        """아직 납부하지 않은 내 청구서 목록과 금액을 조회합니다(납기일이 빠른 순)."""
        ctx = get_context(config)
        return _query("billing.get_unpaid_bills", {"owner_id": ctx.requester_id}, config)

    return [
        rename_account,
        transfer_money,
        confirm_conditional_transfer,
        transfer_split,
        block_card_as_lost,
        lock_card_temporarily,
        unlock_card,
        request_card_reissue,
        change_reissue_delivery_address,
        cancel_card_reissue_request,
        pay_bill,
        pay_bills,
        calculate_conditional_transfer,
        get_account,
        get_my_accounts,
        get_my_total_balance,
        get_transactions,
        get_card,
        get_my_cards,
        get_reissue_request,
        get_reissue_requests_by_card,
        get_my_unpaid_bills,
    ]
