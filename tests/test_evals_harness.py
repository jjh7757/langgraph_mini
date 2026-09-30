"""evals/ 하네스와 evaluator를 가짜 LLM으로 검증 — 실제 Gemini/LangSmith 없이 돈다.

여기서 확인하는 건 "평가 도구가 제대로 채점하는가"이지 Agent 품질이 아니다.
"""

import pytest
from langchain_core.messages import AIMessage

pytest.importorskip("agentevals")

from evals.evaluators import (  # noqa: E402
    evaluate_allowed_tools,
    evaluate_approval,
    evaluate_forbidden_text,
    evaluate_required_tools,
    evaluate_state,
)
from evals.golden_set import GOLDEN_SET, QUERY_TOOLS, select_cases  # noqa: E402
from evals.harness import SEED_NAMES, build_env, make_target, snapshot  # noqa: E402
from langgraph_mini.agent.confirmation import ConfirmationDecision  # noqa: E402


class _ScriptedLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return self._responses.pop(0)


class _ScriptedConfirmationLLM:
    def __init__(self, decisions):
        self._decisions = list(decisions)

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return self._decisions.pop(0)


def _call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def _run(case_id, llm_responses, decisions):
    case = next(c for c in GOLDEN_SET if c["case_id"] == case_id)
    target = make_target(_ScriptedLLM(llm_responses), _ScriptedConfirmationLLM(decisions))
    return case, target(case["inputs"])


def _score(evaluator, case, outputs):
    params = {"inputs": case["inputs"], "outputs": outputs, "reference_outputs": case["reference"]}
    import inspect

    accepted = inspect.signature(evaluator).parameters
    return evaluator(**{k: v for k, v in params.items() if k in accepted})


def _transfer_llm(amount=100000):
    return [
        _call("get_my_accounts", {}, "c1"),
        _call("transfer_money", {"from_id": "demo-acc-1", "to_id": "demo-acc-2", "amount": amount}, "c2"),
        AIMessage(content="이체를 처리했어요."),
    ]


# ── golden set 자체의 유효성 ─────────────────────────────────────────


def test_golden_set_has_24_unique_cases_with_valid_seeds():
    ids = [c["case_id"] for c in GOLDEN_SET]
    assert len(ids) == 24
    assert len(set(ids)) == 24
    assert all(c["inputs"]["seed"] in SEED_NAMES for c in GOLDEN_SET)


def test_golden_set_reply_counts_match_expected_interrupts():
    for case in GOLDEN_SET:
        expected = case["reference"]["expected_interrupts"]
        replies = case["inputs"]["replies"]
        high = expected if isinstance(expected, int) else expected[1]
        assert len(replies) >= high, case["case_id"]
        if isinstance(expected, int):
            assert len(replies) == expected, case["case_id"]
            assert len(case["reference"]["expected_interrupt_actions"]) == expected, case["case_id"]


def test_golden_set_expected_calls_are_within_allowed_tools():
    for case in GOLDEN_SET:
        allowed = set(case["reference"]["allowed_tools"])
        for call in case["reference"]["expected_calls"]:
            assert call["name"] in allowed, (case["case_id"], call["name"])
        assert set(QUERY_TOOLS) <= allowed


def test_select_cases_filters_by_priority_and_ids():
    required = select_cases("필수")
    assert required and all(c["priority"] == "필수" for c in required)
    assert len(select_cases("all")) == 24
    assert [c["case_id"] for c in select_cases(case_ids=["accounts"])] == ["accounts"]
    with pytest.raises(ValueError):
        select_cases(case_ids=["nope"])


# ── 시드와 스냅샷 ─────────────────────────────────────────────────────


def test_seeds_apply_expected_state():
    assert snapshot(build_env("S0"))["accounts"]["demo-acc-1"] == 500000
    assert snapshot(build_env("S1"))["cards"]["demo-card-1"] == "분실정지"
    s2 = snapshot(build_env("S2"))
    assert s2["reissue_by_card"]["demo-card-1"][0]["delivery_address"] == "집"
    assert snapshot(build_env("S3"))["accounts"]["demo-acc-5"] == 300000
    assert snapshot(build_env("S4"))["bills"]["demo-bill-1"] == "납부완료"
    assert snapshot(build_env("S6"))["cards"]["demo-card-1"] == "일시잠금"


def test_envs_are_isolated_between_builds():
    first = build_env("S0")
    second = build_env("S0")
    account = first.account_repo.find_by_id("demo-acc-1")
    account.withdraw(1000)
    first.account_repo.save(account)
    assert snapshot(second)["accounts"]["demo-acc-1"] == 500000


# ── 하네스 실행 (가짜 LLM) ────────────────────────────────────────────


def test_transfer_approve_end_to_end_passes_all_deterministic_evaluators():
    case, outputs = _run("transfer_approve", _transfer_llm(), [ConfirmationDecision(action="approve")])

    assert outputs["state"]["accounts"]["demo-acc-1"] == 400000
    assert outputs["state"]["accounts"]["demo-acc-2"] == 2100000
    assert outputs["approval"]["actions"] == ["account.transfer"]
    assert outputs["approval"]["used_replies"] == ["응 진행해줘"]
    for evaluator in (
        evaluate_required_tools,
        evaluate_allowed_tools,
        evaluate_approval,
        evaluate_state,
        evaluate_forbidden_text,
    ):
        assert _score(evaluator, case, outputs)["score"] is True, evaluator.__name__


def test_interrupted_tool_is_recorded_once_despite_rerun_on_resume():
    _, outputs = _run("transfer_approve", _transfer_llm(), [ConfirmationDecision(action="approve")])

    names = [call["name"] for call in outputs["tool_calls"]]
    assert names == ["get_my_accounts", "transfer_money"]
    assert outputs["tool_calls"][1]["args"] == {"from_id": "demo-acc-1", "to_id": "demo-acc-2", "amount": 100000}


def test_transfer_reject_keeps_state_unchanged_but_still_records_proposal_call():
    case, outputs = _run("transfer_reject", _transfer_llm(), [ConfirmationDecision(action="reject")])

    assert [c["name"] for c in outputs["tool_calls"]] == ["get_my_accounts", "transfer_money"]
    assert outputs["state"] == outputs["initial_state"]
    assert _score(evaluate_state, case, outputs)["score"] is True
    assert _score(evaluate_required_tools, case, outputs)["score"] is True


def test_transfer_revise_counts_two_interrupts_and_applies_revised_amount():
    case, outputs = _run(
        "transfer_revise",
        _transfer_llm(),
        [
            ConfirmationDecision(action="revise", new_params={"amount": 50000}),
            ConfirmationDecision(action="approve"),
        ],
    )

    assert outputs["approval"]["interrupt_count"] == 2
    assert outputs["approval"]["used_replies"] == ["아니 5만 원으로 바꿔줘", "응 그걸로 진행해"]
    assert outputs["state"]["accounts"]["demo-acc-1"] == 450000
    assert _score(evaluate_approval, case, outputs)["score"] is True
    assert _score(evaluate_state, case, outputs)["score"] is True


def test_missing_amount_without_tool_call_passes_and_no_interrupt():
    llm = [AIMessage(content="얼마를 보낼까요?")]
    case, outputs = _run("missing_amount", llm, [])

    assert outputs["tool_calls"] == []
    assert outputs["answer"] == "얼마를 보낼까요?"
    assert outputs["approval"]["interrupt_count"] == 0
    for evaluator in (evaluate_allowed_tools, evaluate_approval, evaluate_state):
        assert _score(evaluator, case, outputs)["score"] is True, evaluator.__name__


def test_missing_reply_leaves_pending_and_fails_approval_flow():
    case = next(c for c in GOLDEN_SET if c["case_id"] == "transfer_approve")
    inputs = {**case["inputs"], "replies": []}
    target = make_target(_ScriptedLLM(_transfer_llm()), _ScriptedConfirmationLLM([]))
    outputs = target(inputs)

    assert outputs["approval"]["pending"] is True
    assert outputs["answer"] == ""
    assert _score(evaluate_approval, {**case, "inputs": inputs}, outputs)["score"] is False


# ── evaluator 단위 동작 ───────────────────────────────────────────────


def test_required_tools_fails_when_amount_differs_but_allowed_tools_passes():
    case = next(c for c in GOLDEN_SET if c["case_id"] == "transfer_approve")
    outputs = {
        "tool_calls": [
            {"name": "get_my_accounts", "args": {}},
            {"name": "transfer_money", "args": {"from_id": "demo-acc-1", "to_id": "demo-acc-2", "amount": 200000}},
        ]
    }

    assert _score(evaluate_required_tools, case, outputs)["score"] is False
    assert _score(evaluate_allowed_tools, case, outputs)["score"] is True


def test_allowed_tools_fails_on_unlisted_tool():
    case = next(c for c in GOLDEN_SET if c["case_id"] == "missing_amount")
    outputs = {"tool_calls": [{"name": "transfer_money", "args": {}}]}

    assert _score(evaluate_allowed_tools, case, outputs)["score"] is False


def test_state_check_detects_unexpected_change_and_wrong_value():
    case = next(c for c in GOLDEN_SET if c["case_id"] == "transfer_reject")
    initial = snapshot(build_env("S0"))
    changed = {**initial, "accounts": {**initial["accounts"], "demo-acc-1": 400000}}

    result = _score(evaluate_state, case, {"initial_state": initial, "state": changed})
    assert result["score"] is False
    assert "demo-acc-1" in result["comment"]

    approve = next(c for c in GOLDEN_SET if c["case_id"] == "transfer_approve")
    wrong = _score(evaluate_state, approve, {"initial_state": initial, "state": initial})
    assert wrong["score"] is False


def test_forbidden_text_catches_leaked_balance():
    case = next(c for c in GOLDEN_SET if c["case_id"] == "other_owner_balance")

    assert _score(evaluate_forbidden_text, case, {"answer": "그 계좌 잔액은 300,000원입니다."})["score"] is False
    assert _score(evaluate_forbidden_text, case, {"answer": "타인 계좌는 조회할 수 없어요."})["score"] is True


def test_approval_range_allows_zero_or_one_interrupt():
    case = next(c for c in GOLDEN_SET if c["case_id"] == "insufficient_balance")
    inputs = case["inputs"]
    none = {"approval": {"interrupt_count": 0, "actions": [], "used_replies": [], "pending": False}}
    one = {"approval": {"interrupt_count": 1, "actions": ["account.transfer"], "used_replies": ["응"], "pending": False}}
    two = {"approval": {"interrupt_count": 2, "actions": ["account.transfer"] * 2, "used_replies": ["응", "응"], "pending": False}}

    assert evaluate_approval(inputs, none, case["reference"])["score"] is True
    assert evaluate_approval(inputs, one, case["reference"])["score"] is True
    assert evaluate_approval(inputs, two, case["reference"])["score"] is False
