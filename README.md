# langgraph-mini

LangGraph 기반 미니 프로젝트.

## 요구 사항

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/)

## 설치

```bash
uv sync
```

## 실행

`.env.example`을 `.env`로 복사하고 [Google AI Studio](https://aistudio.google.com/apikey)에서
발급받은 키를 `GOOGLE_API_KEY`에 채운 뒤:

```bash
uv run langgraph-mini
```

터미널에서 계좌/카드/청구서 관련 대화를 할 수 있습니다. 데이터는 `data/*.json`에 저장되고
(첫 실행 시 데모용 계좌·카드·청구서를 자동으로 만들어줌), 프로그램을 껐다 켜도 잔액·카드
상태·승인 대기 중이던 요청이 그대로 남아있습니다.
