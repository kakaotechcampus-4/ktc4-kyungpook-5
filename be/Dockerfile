FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# 바이트코드를 미리 컴파일해 --reload 재시작을 빠르게 한다.
# 바인드 마운트 위에서는 하드링크를 걸 수 없어 copy 로 바꾼다.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 의존성만 먼저 설치해 레이어로 굳힌다. app/ 이 바뀌어도 재설치하지 않는다.
# --no-install-project: WORKDIR 에 app/ 이 있어 그대로 import 되므로 패키지 설치가 필요 없다.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY app ./app

EXPOSE 8000

# --no-sync: 실행 시점에 uv 가 프로젝트를 다시 설치하려 하지 않게 한다.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]
