"""계좌 이체 서비스 패키지.

구조 (설계초안/3_개선설계_서비스분리.png, 설계초안/구현_가이드라인.md 참고):
    domain.py                Account/Transaction 도메인 모델 + 예외
    repository.py            AccountRepository protocol + InMemoryAccountRepository
    transaction_repository.py TransactionRepository protocol + MemoryTransactionRepository
    services/
        query.py     AccountQueryService (카드결제 내역 조회 시 card 패키지의
                     CardRepository를 가져다 씀 — 반대 방향 의존은 없음)
        transfer.py   AccountTransferService
        manage.py     AccountManageService

Card 도메인/서비스는 langgraph_mini.card 패키지로 분리돼 있음(account와 동급).
"""
