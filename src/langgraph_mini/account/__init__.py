"""계좌 이체 서비스 패키지.

구조 (설계초안/3_개선설계_서비스분리.png, 설계초안/구현_가이드라인.md 참고):
    domain.py      Account, Transaction 도메인 모델 + 예외
    repository.py  AccountRepository protocol + InMemoryAccountRepository
    services/      AccountQueryService / AccountTransferService / AccountManageService
"""
