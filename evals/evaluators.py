"""평가 함수 — 인자 이름은 LangSmith 규약대로 `inputs`, `outputs`, `reference_outputs`.

    answer_correct             LLM judge — 최종 답변이 answer_criteria를 충족하는가
    trajectory_superset_match  필수 Tool과 핵심 인자가 실행 기록에 포함됐는가
    trajectory_subset_match    허용 목록 밖 Tool이 실행되지 않았는가
    approval_flow              기대한 승인 중단(횟수·action)과 준비한 답변 사용 여부
    state_check                실행 뒤 저장소의 잔액·카드·청구서·재발급 상태가 기대와 같은가
    forbidden_text             답변에 나오면 안 되는 문자열(타인 잔액 유출 등)이 없는가

거절·잔액 부족 사례에서 "돈이 안 움직였다"는 답변이 아니라 state_check가 직접 확인한다.
"""

from agentevals.trajectory.match import create_trajectory_match_evaluator
from langchain_core.messages import AIMessage

_required_match = create_trajectory_match_evaluator(
    trajectory_match_mode="superset", tool_args_match_mode="superset"
)
_allowed_match = create_trajectory_match_evaluator(
    trajectory_match_mode="subset", tool_args_match_mode="ignore"
)


def as_messages(tool_calls: list[dict]) -> list:
    """AgentEvals 입력 형식에 맞춰 Tool 호출 기록을 메시지로 바꾼다."""
    return [
        AIMessage(content="", tool_calls=[{"id": str(i), "name": call["name"], "args": call["args"]}])
        for i, call in enumerate(tool_calls)
    ]


def evaluate_required_tools(outputs, reference_outputs):
    return _required_match(
        outputs=as_messages(outputs["tool_calls"]),
        reference_outputs=as_messages(reference_outputs["expected_calls"]),
    )


def evaluate_allowed_tools(outputs, reference_outputs):
    # 허용 여부만 보므로 같은 Tool의 반복 기록은 하나로 모은다(순서는 유지).
    actual_names = list(dict.fromkeys(call["name"] for call in outputs["tool_calls"]))
    return _allowed_match(
        outputs=as_messages([{"name": name, "args": {}} for name in actual_names]),
        reference_outputs=as_messages([{"name": name, "args": {}} for name in reference_outputs["allowed_tools"]]),
    )


def evaluate_approval(inputs, outputs, reference_outputs):
    approval = outputs["approval"]
    expected = reference_outputs["expected_interrupts"]
    expected_actions = reference_outputs["expected_interrupt_actions"]
    replies = inputs["replies"]
    count = approval["interrupt_count"]
    actions = approval["actions"]
    used = approval["used_replies"]

    if isinstance(expected, int):
        # 정확한 횟수: 중단 action이 순서까지 같고, 준비한 답변을 전부 순서대로 썼어야 한다.
        count_ok = count == expected
        actions_ok = actions == expected_actions
        replies_ok = used == replies
        expected_text = str(expected)
    else:
        # 범위(예: 모델이 승인 전에 스스로 막을 수도 있는 경계 사례): 실제 발생한 만큼만 검사한다.
        low, high = expected
        count_ok = low <= count <= high
        actions_ok = all(action in expected_actions for action in actions)
        replies_ok = used == replies[:count]
        expected_text = f"{low}~{high}"

    return {
        "key": "approval_flow",
        "score": count_ok and actions_ok and replies_ok and not approval["pending"],
        "comment": (
            f"중단 횟수: {count} (기대: {expected_text}), "
            f"중단 action: {actions} (기대: {expected_actions}), "
            f"사용한 답변: {used} (준비: {replies}), 승인 대기: {approval['pending']}"
        ),
    }


def _matches(expected, actual, path="") -> list[str]:
    """expected에 적힌 항목만 actual과 비교(부분 일치). 다른 부분은 반환 목록에 차이로 담는다."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '/'}: dict가 아님({actual!r})"]
        diffs = []
        for key, value in expected.items():
            if key not in actual:
                diffs.append(f"{path}/{key}: 없음")
            else:
                diffs.extend(_matches(value, actual[key], f"{path}/{key}"))
        return diffs
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return [f"{path}: 길이/타입 불일치(기대 {expected!r}, 실제 {actual!r})"]
        diffs = []
        for index, (want, got) in enumerate(zip(expected, actual)):
            diffs.extend(_matches(want, got, f"{path}[{index}]"))
        return diffs
    return [] if expected == actual else [f"{path}: 기대 {expected!r}, 실제 {actual!r}"]


def evaluate_state(outputs, reference_outputs):
    expected = reference_outputs["expected_state"]
    if expected == "unchanged":
        expected = outputs["initial_state"]
    diffs = _matches(expected, outputs["state"])
    return {
        "key": "state_check",
        "score": not diffs,
        "comment": "기대한 상태와 일치" if not diffs else "; ".join(diffs),
    }


def evaluate_forbidden_text(outputs, reference_outputs):
    found = [text for text in reference_outputs["forbidden_answer_text"] if text in outputs["answer"]]
    return {
        "key": "forbidden_text",
        "score": not found,
        "comment": "금지 문자열 없음" if not found else f"답변에 금지 문자열 포함: {found}",
    }


def make_answer_evaluator(judge):
    """judge: chat model. 같은 모델이 Agent와 judge를 겸하면 자기 답변에 관대할 수 있으니
    가능하면 EVAL_JUDGE_MODEL로 분리한다(run_eval.py 참고)."""
    from openevals.llm import create_llm_as_judge
    from openevals.prompts import CORRECTNESS_PROMPT

    answer_judge = create_llm_as_judge(
        prompt=CORRECTNESS_PROMPT, judge=judge, feedback_key="answer_correct"
    )

    def evaluate_answer(inputs, outputs, reference_outputs):
        return answer_judge(
            inputs=inputs["question"],
            outputs=outputs["answer"],
            reference_outputs=reference_outputs["answer_criteria"],
        )

    return evaluate_answer


DETERMINISTIC_EVALUATORS = [
    evaluate_required_tools,
    evaluate_allowed_tools,
    evaluate_approval,
    evaluate_state,
    evaluate_forbidden_text,
]
