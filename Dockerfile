# ghcr.io/astral-sh/uv:python3.13-bookworm-slim은 멀티arch(arm64 포함) — GitHub Actions가
# --platform linux/arm64로 빌드하므로(TIL 배포 문서 참고, 서버가 Graviton/arm64) 이 베이스
# 이미지 자체는 특별히 손댈 게 없다.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "langgraph_mini.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
