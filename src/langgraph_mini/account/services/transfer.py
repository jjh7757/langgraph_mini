"""계좌 이체 관련 서비스 (즉시/조건부/분할).

이체 한 건마다 거래 내역(Transaction)이 계좌별로 2건 생성됨(TRANSFER_OUT/TRANSFER_IN) —
domain.Transaction의 docstring 참고. 그래서 이체 메서드들의 반환 타입은 전부
list[Transaction] (단일 Transaction이 아님).

조건부 이체:
    "승인 후 처리" + "실행 전 잔액이 달라지면 재승인"을 만족시키려면 계산과 실행 사이에
    시간차가 있어야 하므로, 단일 호출이 아니라 2단계(calculate → confirm)로 나눔.

    1) calculate_conditional_transfer(from_id, to_id, condition)
       → 이체액(= 출금 계좌 잔액 - remaining_balance)을 계산만 하고 실행하지 않음.
         계산된 이체액이 0 이하면 ConditionalTransferNotNeededError.
         결과(ConditionalTransferQuote)를 사용자에게 보여주고 승인을 받음.
    2) 승인되면 confirm_conditional_transfer(quote)
       → 실행 시점 출금 계좌 잔액이 quote.balance_snapshot과 다르면
         StaleConditionalTransferError (재승인 또는 재요청 필요).
         같으면 quote.amount만큼 실제 이체 실행.

여러 계좌로 나눠 이체:
    targets: [(계좌id, 금액), ...]. 각 금액은 0보다 큰 정수, 출금 계좌 잔액은
    총액(targets 금액 합) 이상이어야 함. "일부만 반영 금지"를 지키려면 계좌를
    하나라도 건드리기 전에 검증을 전부 끝내야 함 (아래 transfer_split 메서드
    docstring에 순서 명시). target마다 TRANSFER_OUT/TRANSFER_IN 한 쌍씩 생성.
"""

from dataclasses import dataclass
from typing import Protocol

from ..domain import Transaction, TransactionType, TransferCondition
from ..repository import AccountRepository
from ..transaction_repository import TransactionRepository


class AccountSelfTransferError(Exception):
    """자기 자신에게 이체하려 할 때."""


class ConditionalTransferNotNeededError(Exception):
    """조건에 따라 계산한 이체액이 0 이하일 때 (remaining_balance가 잔액 이상 등)."""


class StaleConditionalTransferError(Exception):
    """calculate_conditional_transfer 이후 잔액이 바뀌어 이체액이 더 이상 유효하지 않을 때.
    재승인 또는 재요청이 필요함을 의미."""


@dataclass
class ConditionalTransferQuote:
    """calculate_conditional_transfer의 결과. 그대로 confirm_conditional_transfer에 넘김."""

    from_id: str
    to_id: str
    amount: int
    balance_snapshot: int  # 계산 시점의 출금 계좌 잔액


class AccountTransferService(Protocol):
    def transfer(self, from_id: str, to_id: str, amount: int) -> list[Transaction]: ...

    def calculate_conditional_transfer(
        self, from_id: str, to_id: str, condition: TransferCondition
    ) -> ConditionalTransferQuote: ...

    def confirm_conditional_transfer(
        self, quote: ConditionalTransferQuote
    ) -> list[Transaction]: ...

    def transfer_split(
        self, from_id: str, targets: list[tuple[str, int]]
    ) -> list[Transaction]: ...


class DefaultAccountTransferService:
    def __init__(
        self, account_repo: AccountRepository, transaction_repo: TransactionRepository
    ) -> None:
        self._account_repo = account_repo
        self._transaction_repo = transaction_repo

    def transfer(self, from_id: str, to_id: str, amount: int) -> list[Transaction]:
        """계좌 잔액 변경(withdraw/deposit/save)은 완성돼 있음.
        TODO(직접 구현): 아래 두 Transaction을 만들어 self._transaction_repo에
        각각 save하고 리스트로 반환할 것.
            Transaction(account_id=from_id, transaction_type=TransactionType.TRANSFER_OUT,
                        amount=amount, counterpart_id=to_id)
            Transaction(account_id=to_id, transaction_type=TransactionType.TRANSFER_IN,
                        amount=amount, counterpart_id=from_id)
        """
        if from_id == to_id:
            raise AccountSelfTransferError
        from_account = self._account_repo.find_by_id(from_id)
        to_account = self._account_repo.find_by_id(to_id)

        from_account.withdraw(amount)
        to_account.deposit(amount)

        self._account_repo.save(from_account)
        self._account_repo.save(to_account)

        raise NotImplementedError

    def calculate_conditional_transfer(
        self, from_id: str, to_id: str, condition: TransferCondition
    ) -> ConditionalTransferQuote:
        """amount = from_account.balance - condition.remaining_balance.
        amount <= 0이면 ConditionalTransferNotNeededError.
        여기서는 계좌 상태를 바꾸지 않음 (조회만)."""
        raise NotImplementedError

    def confirm_conditional_transfer(
        self, quote: ConditionalTransferQuote
    ) -> list[Transaction]:
        """현재 from 계좌 잔액이 quote.balance_snapshot과 다르면
        StaleConditionalTransferError. 같으면 quote.amount로 self.transfer()와
        동일한 흐름 실행 (재사용해도 됨: self.transfer(quote.from_id, quote.to_id, quote.amount))."""
        raise NotImplementedError

    def transfer_split(
        self, from_id: str, targets: list[tuple[str, int]]
    ) -> list[Transaction]:
        """순서가 원자성을 좌우함 — 계좌를 하나라도 건드리기 전에 검증부터 끝낼 것:
        1) targets의 모든 금액이 0보다 큰지 검증 (하나라도 아니면 ValueError,
           이 시점까지는 어떤 계좌도 안 건드린 상태)
        2) 모든 대상 계좌를 find_by_id로 미리 조회
           (존재 안 하는 id가 있으면 AccountNotFoundError, 역시 아직 안전)
        3) 총액 = sum(targets의 금액) 계산 후 from_account.withdraw(총액) 1회 호출
           (잔액 부족하면 InsufficientBalanceError, 아직 대상 계좌들은 안 바뀐 상태)
        4) 그제서야 각 대상 계좌에 deposit
        5) from_account + 모든 대상 계좌 save
        6) target마다 TRANSFER_OUT(from_id 기준)/TRANSFER_IN(대상 계좌 기준) 한 쌍씩
           만들어 transaction_repo에 save, 전부 리스트로 반환
        """
        raise NotImplementedError
