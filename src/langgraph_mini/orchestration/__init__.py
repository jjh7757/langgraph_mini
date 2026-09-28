"""Orchestration Service 패키지.

설계 전체는 설계초안/오케스트레이션_설계.md 참고. 구조:
    domain.py               PendingRequest/PendingStatus/ActionResult + 예외
    pending_repository.py    PendingRepository protocol + MemoryPendingRepository
    completed_repository.py  CompletedRequestRepository protocol + MemoryCompletedRequestRepository
    ownership.py              리소스별(Account/Card/ReissueRequest/Bill) 소유권 검증 함수
    actions.py                 ActionSpec + Services/Repos 컨테이너 + build_actions() 레지스트리
    service.py                 OrchestrationService — query(즉시 실행) /
                                propose·revise·approve·reject(승인 흐름) /
                                get_pending·get_history(복구·후속 조회)

account/card/billing 서비스 protocol만 알고 구현체는 모름 (Services 컨테이너로 주입받음).
자연어 해석(추가 질문, 대화 대상 확인, 자연어 승인/취소)은 전부 Agent 몫 — Orchestration은
항상 이미 해석된 action/params/request_id만 받는다.
"""
