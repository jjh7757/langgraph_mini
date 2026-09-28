"""청구(Billing) 서비스 패키지.

구조 (account/, card/ 패키지와 같은 패턴):
    domain.py       Bill 도메인 모델 + 예외
    repository.py   BillRepository protocol + MemoryBillRepository
    services/
        query.py    BillingQueryService (미납 청구서 조회)
        pay.py      BillPaymentService (단건/일괄 납부 — account 패키지의
                    AccountRepository/TransactionRepository를 가져다 씀)
"""
