"""LangGraph 연동 패키지.

설계 전체는 설계초안/에이전트_설계.md 참고. 구조:
    context.py          AgentContext(requester_id/thread_id) + get_context()
    confirmation.py       승인 루프(propose_and_confirm/resume_and_confirm) +
                          자연어 답변 분류(classify_confirmation)
    propose_tools.py      build_tools() — @tool 함수 22개 (실행형 12 + 조회형 10,
                          orchestration/actions.py의 ACTIONS와 1:1 대응)
    graph.py               build_graph() — StateGraph 조립(복구 체크 → 에이전트 → ToolNode)
    wiring.py               build_orchestration() — 실제 JSON 파일로 OrchestrationService 조립

Client -> LangGraph Agent -> Propose Tools -> Orchestration. 도메인 서비스는 직접
호출하지 않음 — 항상 orchestration을 거침.
"""
