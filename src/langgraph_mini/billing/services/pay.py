"""청구서 납부 서비스 (단건 / 일괄).

계좌 잔액 차감과 거래 내역 기록은 billing이 스스로 만들지 않고 account 패키지의
AccountRepository/TransactionRepository·Transaction을 그대로 가져다 씀 — billing은
청구서 상태(Bill.status)만 스스로 관리함 (card/services/query.py가 account를 가져다
쓰는 것과 같은 방향의 의존, 반대 방향은 없음).

단건 납부와 일괄 납부의 "이미 납부된 건" 처리 방식이 다름 — 의도한 차이:
    - 단건(pay_bill): 사용자가 특정 청구서를 콕 집어 납부해달라고 한 것이므로,
      이미 납부됐으면 BillAlreadyPaidError를 그대로 올려서 알림("다시 처리하지 않는다").
    - 일괄(pay_bills): 미납 청구서를 한꺼번에 처리하는 거라 그중 하나가 이미
      납부돼 있어도 에러가 아니라 "이미 완료됨"으로 보고 다음 건을 계속 진행
      ("이미 저장된 납부는 유지").
"""

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ...account.domain import InsufficientBalanceError, Transaction, TransactionType
from ...account.repository import AccountRepository
from ...account.transaction_repository import TransactionRepository
from ..domain import Bill, BillAlreadyPaidError, BillStatus
from ..repository import BillRepository


@dataclass
class BillPaymentResult:
    """pay_bill 한 건의 결과."""

    bill: Bill
    transaction: Transaction


class BillPaymentOutcome(Enum):
    COMPLETED = "완료"
    FAILED = "실패"  # 잔액 부족 — 미납 상태 그대로 유지, 다음 건 계속
    UNPROCESSED = "미처리"  # 저장 실패로 중단된 이후 건(본인 포함) — 아무것도 반영 안 됨


@dataclass
class BillPaymentAttempt:
    """pay_bills 중 청구서 한 건의 처리 결과."""

    bill_id: str
    outcome: BillPaymentOutcome
    transaction: Transaction | None = None  # COMPLETED일 때만(이미 납부돼 있던 건은 None)


class BillPaymentService(Protocol):
    def pay_bill(self, bill_id: str, account_id: str) -> BillPaymentResult: ...

    def pay_bills(
        self, account_id: str, bill_ids: list[str]
    ) -> list[BillPaymentAttempt]: ...


class DefaultBillPaymentService:
    def __init__(
        self,
        bill_repo: BillRepository,
        account_repo: AccountRepository,
        transaction_repo: TransactionRepository,
    ) -> None:
        self._bill_repo = bill_repo
        self._account_repo = account_repo
        self._transaction_repo = transaction_repo

    def pay_bill(self, bill_id: str, account_id: str) -> BillPaymentResult:
        """순서(검증부터 끝내고 나서 실행 — 뭔가 실패했을 때 이미 mutate된 게 남지 않도록):
        1) 상태만 확인 — 이미 PAID면 BillAlreadyPaidError (아직 아무것도 안 건드림)
        2) account.withdraw(bill.amount) — 잔액 부족하면 InsufficientBalanceError
           (Account.withdraw는 부족하면 mutate 전에 예외를 던지므로 여기서 실패해도
           계좌·청구서 둘 다 그대로)
        3) 여기까지 왔으면 전부 성공 확정 — 그제서야 bill.pay()로 상태를 바꾸고 저장.
           (bill.pay()를 withdraw보다 먼저 하면 안 됨 — find_by_id가 돌려주는 건 저장소
           안의 객체와 같은 참조라서, withdraw가 실패해도 이미 PAID로 바뀐 채 남아버림)"""
        bill = self._bill_repo.find_by_id(bill_id)
        if bill.status is BillStatus.PAID:
            raise BillAlreadyPaidError(bill_id)

        account = self._account_repo.find_by_id(account_id)
        account.withdraw(bill.amount)

        bill.pay()
        transaction = Transaction(
            account_id=account_id,
            transaction_type=TransactionType.BILL_PAYMENT,
            amount=bill.amount,
            bill_id=bill.bill_id,
        )
        self._bill_repo.save(bill)
        self._transaction_repo.save(transaction)
        self._account_repo.save(account)

        return BillPaymentResult(bill=bill, transaction=transaction)

    def pay_bills(
        self, account_id: str, bill_ids: list[str]
    ) -> list[BillPaymentAttempt]:
        """순서:
        1) bill_ids 전부 find_by_id로 미리 조회 (없는 id 있으면 BillNotFoundError,
           이 시점까지는 계좌도 청구서도 아무것도 안 건드림)
        2) due_date 오름차순 정렬 — "납기일이 빠른 청구서부터"
        3) account는 한 번만 조회해서 매 건 재사용 (건마다 잔액이 누적으로 줄어듦)
        4) 건별로:
           - 이미 PAID면 재처리 없이 COMPLETED(transaction=None)로 기록하고 다음 건
           - UNPAID면 account의 복사본(account_attempt)에 withdraw 시도
             - InsufficientBalanceError → FAILED로 기록(원본 account·청구서 변경 없음), 다음 건 계속
             - 성공 → bill 복사본(bill_attempt)에 pay() 적용, bill_attempt/transaction/
               account_attempt 순서로 저장 시도(잔액 저장을 제일 마지막에 두는 이유는
               코드 주석 참고)
               - 저장 중 예외 발생 → 이 건 + 남은 모든 건을 UNPROCESSED로 기록하고 즉시 중단
                 (원본 account/bill은 그대로라 정말 "미반영" — 이미 저장 성공한 이전 건들은 유지)
               - 저장 성공 → 그제서야 account를 account_attempt로 교체(다음 건이 이 잔액을
                 이어받음), COMPLETED로 기록(transaction 포함)

        복사본에서 작업하는 이유: find_by_id가 돌려주는 bill/account는 저장소 dict 안의
        객체와 같은 참조라서, 원본에 직접 pay()/withdraw()를 걸었다가 저장이 실패하면
        (save를 안 불렀거나 실패해도) 이미 메모리상 상태가 바뀐 채로 남아 "미반영"이
        지켜지지 않음. 저장 단계의 예외는 지금 MemoryBillRepository/MemoryAccountRepository
        에서는 나지 않지만, 나중에 파일/DB 기반 저장소로 바뀌면 날 수 있어서 일부러
        넓게(Exception) 잡아둔 것 — "파일 저장에 실패하면 처리 중단" 요구사항 그대로."""
        bills = [self._bill_repo.find_by_id(bill_id) for bill_id in bill_ids]
        bills.sort(key=lambda bill: bill.due_date)

        account = self._account_repo.find_by_id(account_id)

        attempts: list[BillPaymentAttempt] = []
        stopped = False

        for bill in bills:
            if stopped:
                attempts.append(
                    BillPaymentAttempt(
                        bill_id=bill.bill_id, outcome=BillPaymentOutcome.UNPROCESSED
                    )
                )
                continue

            if bill.status is BillStatus.PAID:
                attempts.append(
                    BillPaymentAttempt(
                        bill_id=bill.bill_id, outcome=BillPaymentOutcome.COMPLETED
                    )
                )
                continue

            account_attempt = copy.deepcopy(account)
            try:
                account_attempt.withdraw(bill.amount)
            except InsufficientBalanceError:
                attempts.append(
                    BillPaymentAttempt(
                        bill_id=bill.bill_id, outcome=BillPaymentOutcome.FAILED
                    )
                )
                continue

            bill_attempt = copy.deepcopy(bill)
            bill_attempt.pay()
            transaction = Transaction(
                account_id=account_id,
                transaction_type=TransactionType.BILL_PAYMENT,
                amount=bill.amount,
                bill_id=bill.bill_id,
            )

            try:
                # 잔액(account) 저장을 제일 마지막에 — 청구서·거래 기록 저장이 실패하면
                # "기록 없이 돈만 빠진" 상태가 생기면 안 되니, 무슨 일이 있었는지 먼저
                # 기록하고 나서 잔액을 반영한다.
                self._bill_repo.save(bill_attempt)
                self._transaction_repo.save(transaction)
                self._account_repo.save(account_attempt)
            except Exception:
                attempts.append(
                    BillPaymentAttempt(
                        bill_id=bill.bill_id, outcome=BillPaymentOutcome.UNPROCESSED
                    )
                )
                stopped = True
                continue

            account = account_attempt
            attempts.append(
                BillPaymentAttempt(
                    bill_id=bill.bill_id,
                    outcome=BillPaymentOutcome.COMPLETED,
                    transaction=transaction,
                )
            )

        return attempts
