"""평가 실행 진입점.

    uv run --group eval python -m evals.run_eval                      # 필수 사례를 LangSmith Experiment로
    uv run --group eval python -m evals.run_eval --priority all        # 권장 사례까지 전부
    uv run --group eval python -m evals.run_eval --cases transfer_approve,transfer_reject
    uv run --group eval python -m evals.run_eval --repeat 3            # 비결정성 대비 3회 반복
    uv run --group eval python -m evals.run_eval --local               # LangSmith 없이 콘솔에만 출력

.env(프로젝트 루트)에서 GOOGLE_API_KEY를 읽는다. LangSmith로 올리려면 LANGSMITH_API_KEY도 필요하다.
모델: GEMINI_MODEL(기본 gemini-2.5-flash), judge는 EVAL_JUDGE_MODEL(없으면 같은 모델).
"""

import argparse
import hashlib
import inspect
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .evaluators import DETERMINISTIC_EVALUATORS, make_answer_evaluator
from .golden_set import REQUIRED, select_cases
from .harness import make_target

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCORE_KEYS = [
    "answer_correct",
    "trajectory_superset_match",
    "trajectory_subset_match",
    "approval_flow",
    "state_check",
    "forbidden_text",
]


def _build_models():
    from langchain_google_genai import ChatGoogleGenerativeAI

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    # cli.py와 같은 설정 — thinking_budget을 고정하지 않으면 tool 22개 조합에서 응답 없이 끝나는 문제가 있음.
    thinking_budget = int(os.environ.get("GEMINI_THINKING_BUDGET", "1024"))
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0, thinking_budget=thinking_budget)
    judge_name = os.environ.get("EVAL_JUDGE_MODEL", model_name)
    judge = ChatGoogleGenerativeAI(model=judge_name, temperature=0)
    return llm, judge, model_name, judge_name


def dataset_name(cases: list[dict]) -> str:
    """사례 내용이 같으면 같은 이름 — 모델·프롬프트를 고친 전후를 같은 Dataset으로 비교하려는 것."""
    digest = hashlib.sha1(
        json.dumps([(c["case_id"], c["inputs"], c["reference"]) for c in cases], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:8]
    return f"langgraph-mini-eval-{digest}"


def _ensure_dataset(client, cases: list[dict]):
    name = dataset_name(cases)
    if client.has_dataset(dataset_name=name):
        return client.read_dataset(dataset_name=name), False
    dataset = client.create_dataset(dataset_name=name, description="langgraph_mini Agent 평가 Golden set")
    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {
                "inputs": case["inputs"],
                "outputs": case["reference"],
                "metadata": {"case_id": case["case_id"], "priority": case["priority"]},
            }
            for case in cases
        ],
    )
    return dataset, True


def run_langsmith(cases, target, evaluators, *, model_name, repeat, concurrency) -> None:
    from langsmith import Client

    client = Client()
    dataset, created = _ensure_dataset(client, cases)
    print(f"Dataset: {dataset.name} ({'새로 생성' if created else '기존 재사용'}, 사례 {len(cases)}개)")
    experiment = client.evaluate(
        target,
        data=dataset.id,
        evaluators=evaluators,
        experiment_prefix="langgraph-mini",
        metadata={"model": model_name},
        num_repetitions=repeat,
        max_concurrency=concurrency,
    )
    print_experiment(experiment)


def print_experiment(experiment) -> None:
    """Experiment 결과를 사례별 점수표로 출력. 점수 없음/평가 오류는 '미채점'으로 구분(통과로 치지 않음)."""
    totals = {key: [0, 0] for key in SCORE_KEYS}
    for row in experiment:
        case_id = (row["example"].metadata or {}).get("case_id", str(row["example"].id))
        print(f"\n[{case_id}] 실행 오류: {row['run'].error or '없음'}")
        feedback = {item.key: item for item in row["evaluation_results"]["results"]}
        for key in SCORE_KEYS:
            item = feedback.get(key)
            if item is None or item.score is None or (item.extra or {}).get("error"):
                print(f"  {key}: 미채점 ({getattr(item, 'comment', None) or '평가 결과 없음'})")
                continue
            passed = bool(item.score)
            totals[key][0] += passed
            totals[key][1] += 1
            print(f"  {key}: {'통과' if passed else '실패'}" + ("" if passed else f" — {item.comment}"))
    print("\n== 요약 (통과/채점됨) ==")
    for key, (passed, graded) in totals.items():
        print(f"  {key}: {passed}/{graded}")


def _call_evaluator(evaluator, case, outputs) -> dict:
    """LangSmith처럼 evaluator가 선언한 인자(inputs/outputs/reference_outputs)만 골라 넘긴다."""
    available = {"inputs": case["inputs"], "outputs": outputs, "reference_outputs": case["reference"]}
    wanted = inspect.signature(evaluator).parameters
    return evaluator(**{name: value for name, value in available.items() if name in wanted})


def run_local(cases, target, evaluators, *, repeat: int = 1) -> None:
    """LangSmith 없이 같은 target/evaluator로 돌려 콘솔에 출력(도구·키 설정 점검용)."""
    totals = {key: [0, 0] for key in SCORE_KEYS}
    for case, attempt in ((case, n) for case in cases for n in range(1, repeat + 1)):
        suffix = f" #{attempt}/{repeat}" if repeat > 1 else ""
        print(f"\n[{case['case_id']}{suffix}] {case['inputs']['question']}  (replies={case['inputs']['replies']})")
        try:
            outputs = target(case["inputs"])
        except Exception as error:  # 실행 오류는 해당 사례만 실패로 남기고 계속한다
            print(f"  실행 오류: {type(error).__name__}: {error}")
            continue
        print(f"  답변: {outputs['answer']!r}")
        print(f"  Tool: {[(c['name'], c['args']) for c in outputs['tool_calls']]}")
        for evaluator in evaluators:
            result = _call_evaluator(evaluator, case, outputs)
            passed = bool(result["score"])
            totals.setdefault(result["key"], [0, 0])
            totals[result["key"]][0] += passed
            totals[result["key"]][1] += 1
            print(f"  {result['key']}: {'통과' if passed else '실패'}" + ("" if passed else f" — {result.get('comment')}"))
    print("\n== 요약 (통과/채점됨) ==")
    for key, (passed, graded) in totals.items():
        if graded:
            print(f"  {key}: {passed}/{graded}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--priority", choices=[REQUIRED, "권장", "all"], default=REQUIRED)
    parser.add_argument("--cases", help="쉼표로 구분한 case_id (주면 --priority 무시)")
    parser.add_argument("--repeat", type=int, default=1, help="각 사례 반복 횟수(--local에서도 동작)")
    parser.add_argument("--concurrency", type=int, default=2, help="동시 실행 수(LangSmith 모드, Gemini 쿼터 고려)")
    parser.add_argument("--local", action="store_true", help="LangSmith에 올리지 않고 콘솔에만 출력")
    args = parser.parse_args(argv)

    # 상위 폴더의 다른 프로젝트 .env를 잘못 읽지 않도록 경로를 명시(cli.py와 같은 이유).
    load_dotenv(PROJECT_ROOT / ".env")

    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        print("GOOGLE_API_KEY(또는 GEMINI_API_KEY)가 없습니다. 프로젝트 루트 .env에 넣어 주세요.")
        return 1
    if not args.local and not os.environ.get("LANGSMITH_API_KEY"):
        print(
            "LANGSMITH_API_KEY가 없습니다. .env에 LANGSMITH_API_KEY를 넣거나, "
            "LangSmith 없이 확인하려면 --local을 쓰세요."
        )
        return 1

    cases = select_cases(args.priority, args.cases.split(",") if args.cases else None)
    llm, judge, model_name, judge_name = _build_models()
    print(f"모델: {model_name}, judge: {judge_name}, 사례 {len(cases)}개")
    if judge_name == model_name:
        print("주의: Agent와 judge가 같은 모델입니다. 자기 답변에 관대할 수 있어 EVAL_JUDGE_MODEL 분리를 권장합니다.")

    target = make_target(llm)
    evaluators = [make_answer_evaluator(judge), *DETERMINISTIC_EVALUATORS]
    if args.local:
        run_local(cases, target, evaluators, repeat=args.repeat)
    else:
        run_langsmith(
            cases, target, evaluators, model_name=model_name, repeat=args.repeat, concurrency=args.concurrency
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
