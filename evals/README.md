# evals — 실제 LLM으로 Agent 품질을 채점하는 평가

`tests/`(pytest, 가짜 LLM, 로직 검증)와 달리 **실제 Gemini**로 Agent를 돌려 LangSmith Experiment로 채점한다.
API 비용과 키가 필요해서 pytest와 분리했다. 사례 설계와 근거는 [평가/평가_목록.md](../평가/평가_목록.md).

## 준비

```bash
uv sync --group eval        # openevals, agentevals 설치 (eval 전용 그룹 — 런타임 의존성에는 안 들어감)
```

프로젝트 루트 `.env`에 다음을 넣는다 (`.env`는 git에 올라가지 않는다).

| 변수 | 필수 | 설명 |
|---|---|---|
| `GOOGLE_API_KEY` | 예 | Agent와 judge가 쓰는 Gemini 키 |
| `LANGSMITH_API_KEY` | LangSmith 모드에서 | Experiment 기록용. `--local`이면 불필요 |
| `GEMINI_MODEL` | 아니오 | 평가할 모델 (기본 `gemini-2.5-flash`) |
| `EVAL_JUDGE_MODEL` | 아니오 | 채점 모델. 안 넣으면 Agent와 같은 모델(자기 답변에 관대할 수 있어 분리 권장) |

## 실행

```bash
uv run --group eval python -m evals.run_eval                            # 필수 사례 15개
uv run --group eval python -m evals.run_eval --priority all             # 권장 포함 24개
uv run --group eval python -m evals.run_eval --cases transfer_approve,transfer_reject
uv run --group eval python -m evals.run_eval --repeat 3                 # 비결정성 대비 3회 반복
uv run --group eval python -m evals.run_eval --local                    # LangSmith 없이 콘솔에만 출력
```

처음에는 `--local --cases accounts`로 키와 도구 설정부터 확인하는 것을 권장한다.

## 구성

| 파일 | 역할 |
|---|---|
| `golden_set.py` | 24개 사례 데이터 (`inputs` / `reference`) |
| `harness.py` | 사례별 격리 환경(시드 S0~S6), Agent 실행, 승인 재개, Tool 기록 수집, 상태 스냅샷 |
| `evaluators.py` | 채점 함수 6종 (`answer_correct`, `trajectory_superset_match`, `trajectory_subset_match`, `approval_flow`, `state_check`, `forbidden_text`) |
| `run_eval.py` | 실행 진입점 (Dataset 생성/재사용, Experiment 실행, 결과 출력) |

같은 사례 내용이면 Dataset 이름이 같아서(`langgraph-mini-eval-<해시>`) 모델·프롬프트를 고친 전후를 같은 Dataset으로 비교할 수 있다.
사례를 바꾸면 해시가 달라져 새 Dataset이 만들어진다.

## 결과 읽기

점수가 없거나 평가 중 오류가 나면 `미채점`으로 표시하며, 통과로 치지 않는다.
실패한 사례는 LangSmith 링크의 Trace에서 실제 Tool 호출과 답변을 확인하고, `state_check`의 comment에서 어떤 잔액·상태가 기대와 달랐는지 본다.

평가 도구 자체의 동작(가짜 LLM)은 `tests/test_evals_harness.py`가 검증한다: `uv run --group eval python -m pytest tests/test_evals_harness.py`.
