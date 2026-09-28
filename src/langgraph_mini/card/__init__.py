"""카드(Card) 서비스 패키지.

구조 (설계초안/5_아키텍처_도메인저장계층_초안.svg 참고, account/ 패키지와 같은 패턴):
    domain.py                      Card/ReissueRequest 도메인 모델 + 예외
    repository.py                  CardRepository protocol + MemoryCardRepository
    reissue_request_repository.py  ReissueRequestRepository protocol + MemoryReissueRequestRepository
    services/
        query.py     CardQueryService
        status.py    CardStatusService (분실정지/일시잠금/잠금해제)
        reissue.py   CardReissueService (재발급 신청/조회/수정·취소)

account 패키지가 카드결제 거래내역 조회 시 이 패키지의 Card/CardRepository를 가져다 씀
(account/services/query.py 참고) — 반대 방향 의존은 없음(card는 account를 import하지 않음,
Card.account_id는 그냥 문자열 id).
"""
