"""OrchestrationService — 소유권 검증/멱등성(request_id)/예외→구조화 결과 변환 +
승인·되묻기·복구 흐름을 전담. 도메인 서비스는 이 중 아무것도 모른다.

자연어 해석(추가 질문, 대화 대상 확인, "응"/"취소" 매핑)은 전부 Agent 몫 — Orchestration은
항상 이미 해석된 action 문자열/params dict/request_id만 받는다 (오케스트레이션_설계.md
10절 "Agent와의 경계" 참고).
"""

from datetime import datetime

from .actions import ActionSpec, Services
from .completed_repository import CompletedRequestRepository
from .domain import (
    ActionNotRegisteredError,
    ActionResult,
    MissingParamsError,
    PendingRequest,
    PendingRequestNotFoundError,
    PendingRequestNotPendingError,
    PendingStatus,
)
from .pending_repository import PendingRepository


class OrchestrationService:
    def __init__(
        self,
        actions: dict[str, ActionSpec],
        services: Services,
        pending_repo: PendingRepository,
        completed_repo: CompletedRequestRepository,
    ) -> None:
        self._actions = actions
        self._services = services
        self._pending_repo = pending_repo
        self._completed_repo = completed_repo

    def query(self, action: str, params: dict, requester_id: str):
        """조회형. 승인 없이 바로 실행.
        1) ACTIONS에서 spec 조회 (없으면 ActionNotRegisteredError)
        2) required_params 확인 (없으면 MissingParamsError)
        3) spec.verify_owner(params, requester_id) — 실패 시 NotOwnerError
        4) spec.execute(params, self._services) 결과 그대로 반환
        (조회는 재시도 비용이 없으니 멱등성/결과 저장 없음 — 예외도 그대로 전파)
        """
        spec = self._get_spec(action)
        self._check_required_params(action, spec, params)
        spec.verify_owner(params, requester_id)
        return spec.execute(params, self._services)

    def propose(
        self, action: str, params: dict, requester_id: str, thread_id: str, request_id: str
    ) -> PendingRequest:
        """실행형 1단계 — 제안만, 아직 도메인 서비스 호출 안 함.
        1) completed_repo.find_by_request_id(request_id) — 있으면 그대로 반환 (멱등성:
           이미 끝난 요청은 다시 안 만듦)
        2) pending_repo에 같은 request_id가 이미 있으면(아직 미승인) 그것도 그대로 반환
           (재제안으로 덮어쓰지 않음 — LangGraph가 같은 노드를 다시 지날 수 있어서)
        3) ACTIONS에서 spec 조회 (없으면 ActionNotRegisteredError)
        4) required_params 확인 (없으면 MissingParamsError — "불완전한 요청" 안전망)
        5) spec.verify_owner(params, requester_id) — 실패 시 NotOwnerError
           (여기서 막히면 PendingRequest 자체를 안 만듦)
        6) 새 PendingRequest(status=PENDING) 만들어 pending_repo에 save, 반환
        """
        completed = self._completed_repo.find_by_request_id(request_id)
        if completed is not None:
            return completed

        existing_pending = self._find_pending_if_exists(request_id)
        if existing_pending is not None:
            return existing_pending

        spec = self._get_spec(action)
        self._check_required_params(action, spec, params)
        spec.verify_owner(params, requester_id)

        request = PendingRequest(
            request_id=request_id,
            thread_id=thread_id,
            requester_id=requester_id,
            action=action,
            params=params,
        )
        self._pending_repo.save(request)
        return request

    def revise(self, request_id: str, new_params: dict, requester_id: str) -> PendingRequest:
        """승인 전 수정 ("아니, 5만 원만"). 새 요청을 만들지 않고 기존 것의 params만 바꿈.
        1) pending_repo.find_by_id(request_id) — 없으면 PendingRequestNotFoundError
        2) status != PENDING이면 PendingRequestNotPendingError (이미 끝난 건 못 고침)
        3) request.params를 new_params로 부분 병합(update) — 언급 안 된 필드는 유지
        4) spec.verify_owner(병합된 params, requester_id) 재검증 (대상 자체가 바뀔 수도 있음)
        5) save 후 반환 — Agent가 이걸로 전체 내용을 다시 보여주고 재승인 받음
        """
        request = self._pending_repo.find_by_id(request_id)
        if request.status is not PendingStatus.PENDING:
            raise PendingRequestNotPendingError(request_id)

        merged_params = {**request.params, **new_params}
        spec = self._get_spec(request.action)
        spec.verify_owner(merged_params, requester_id)

        request.params = merged_params
        self._pending_repo.save(request)
        return request

    def approve(self, request_id: str) -> ActionResult:
        """실행형 2단계 — 사용자가 승인한 뒤 실제로 실행.
        1) pending_repo.find_by_id(request_id) — 없으면 PendingRequestNotFoundError
        2) status != PENDING이면 PendingRequestNotPendingError
        3) spec.execute(request.params, self._services) 호출
           - 성공: ActionResult(success=True, value=결과), status=EXECUTED
           - 도메인 예외 발생: ActionResult(success=False, error_type=.., error_message=..),
             status=FAILED (도메인 예외 종류가 수십 가지라 여기서만 의도적으로 넓게 잡음 —
             "예외 → 구조화 결과 변환"이 Orchestration의 책임이라 다른 곳에선 안 함)
        4) request.result = 그 ActionResult, resolved_at 채워서 pending_repo.save +
           completed_repo.save (둘 다 저장 — Pending 쪽은 나중에 TTL로 사라지고,
           Completed 쪽이 영구 근거)
        5) ActionResult 반환
        """
        request = self._pending_repo.find_by_id(request_id)
        if request.status is not PendingStatus.PENDING:
            raise PendingRequestNotPendingError(request_id)

        spec = self._get_spec(request.action)
        try:
            value = spec.execute(request.params, self._services)
        except Exception as exc:  # noqa: BLE001 — 의도적으로 넓게 잡음(위 docstring 참고)
            result = ActionResult(
                success=False, error_type=type(exc).__name__, error_message=str(exc)
            )
            request.status = PendingStatus.FAILED
        else:
            result = ActionResult(success=True, value=value)
            request.status = PendingStatus.EXECUTED

        request.result = result
        request.resolved_at = datetime.now()
        self._pending_repo.save(request)
        self._completed_repo.save(request)
        return result

    def reject(self, request_id: str) -> PendingRequest:
        """사용자가 거절 — status=REJECTED로 바꾸고 completed_repo에도 기록(거절도 종결이라
        멱등성/후속 조회 대상). 도메인 서비스는 호출 안 함."""
        request = self._pending_repo.find_by_id(request_id)
        if request.status is not PendingStatus.PENDING:
            raise PendingRequestNotPendingError(request_id)

        request.status = PendingStatus.REJECTED
        request.resolved_at = datetime.now()
        self._pending_repo.save(request)
        self._completed_repo.save(request)
        return request

    def get_pending(self, thread_id: str) -> list[PendingRequest]:
        """이 스레드의 PENDING 상태 요청들. 용도 세 가지:
        - 자연어 승인/취소: Agent가 "응"/"취소"를 어떤 request_id에 매핑할지 여기서 찾음
        - 재시작 복구: 프로세스가 다시 뜬 뒤 이 스레드에 진행 중이던 게 있었는지 확인
        - "지금 뭐 승인 대기 중이야?" 같은 직접 질문
        복구 시에도 여기서 나온 걸 그냥 실행하는 게 아니라 사용자에게 다시 보여주고
        새 approve() 호출을 받아야 함 — PENDING 상태만으로 자동 실행 금지."""
        return [
            request
            for request in self._pending_repo.find_by_thread_id(thread_id)
            if request.status is PendingStatus.PENDING
        ]

    def get_history(self, thread_id: str) -> list[PendingRequest]:
        """후속 결과 조회("아까 이체가 됐어?"). completed_repo.find_by_thread_id 그대로
        위임 — 각 PendingRequest.status/result로 성공/실패/거절 여부와 처리 내용을 알 수 있음."""
        return self._completed_repo.find_by_thread_id(thread_id)

    def _get_spec(self, action: str) -> ActionSpec:
        spec = self._actions.get(action)
        if spec is None:
            raise ActionNotRegisteredError(action)
        return spec

    @staticmethod
    def _check_required_params(action: str, spec: ActionSpec, params: dict) -> None:
        missing = [name for name in spec.required_params if name not in params]
        if missing:
            raise MissingParamsError(action, missing)

    def _find_pending_if_exists(self, request_id: str) -> PendingRequest | None:
        try:
            return self._pending_repo.find_by_id(request_id)
        except PendingRequestNotFoundError:
            return None
