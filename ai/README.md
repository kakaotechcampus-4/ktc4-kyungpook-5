# 운영해 · AI

행사 계획 생성·수정, 과거 기록 검색, 운영 중 변경에 대한 대응안 제안을 담당합니다.

현재는 **디렉터리 구조만 정의한 단계**입니다. Python 파일에는 역할 설명만 있으며, API·Agent·상태 저장은 구현되지 않았습니다.

## 기술 스택

| 항목 | 선택 | 결정 이유 / 메모 |
| --- | --- | --- |
| 언어 | Python 3.12 | BE와 통일 |
| API 프레임워크 | FastAPI | BE가 호출하는 내부 AI API |
| LLM 제공자 | Anthropic | 구체적인 모델·버전은 구현 시 결정 |
| 실행 흐름 관리 | LangGraph | 질문·수정·재계획의 분기와 실행 상태 관리 |
| LLM 연동 구성요소 | LangChain 선택적 사용 | 필요한 모델·도구 연동만 사용 |
| 패키지 관리 | uv | `pyproject.toml`과 `uv.lock`으로 의존성 관리 |
| 프롬프트 관리 | 기능별 `prompts/` | 담당 기능의 처리 코드와 함께 관리 |
| 챗봇 응답 방식 | 동기 (스트리밍 미사용) | 현재 FE 방향에 맞춰 답변을 한 번에 반환 |
| 테스트 | 기능 구현 시 추가 | 현재는 `tests/` 폴더만 구성 |
| 린트 · 포맷 | 미정 | 첫 구현에서 도구와 실행 명령 결정 |

### 확인이 필요한 항목

- BE 연동 계약과 담당 범위
- 계획 대화·실행 체크포인트의 저장 방식과 세션 식별자
- 기록 검색 방식과 자료 정제·색인·저장 방식
- AI 서비스 배포 환경과 로컬 Docker Compose 포함 범위

## 반드시 지켜야 할 3가지 규칙

1. 기능별 처리는 `features/`에 두고, 기능 간 연결·분기는 `workflow/`에서 관리한다. 기능끼리 내부 구현을 직접 import하지 않는다.
2. 회계·계산은 결정론적 코드와 Tool로 처리한다. LLM이 계산 결과를 임의로 만들거나 보정하지 않는다.
3. 기록을 근거로 제시할 때 출처와 원문 위치를 포함한다. 근거가 없으면 없다고 답하고, 가정은 사실과 구분한다.

## 폴더 구조

```text
ai/
├── app/
│   ├── main.py             # FastAPI 앱 구성
│   ├── api.py              # 내부 AI API
│   ├── config.py           # 환경변수·설정
│   ├── llm.py              # 공통 모델 설정
│   ├── schemas.py          # 공통 API 요청·응답
│   ├── workflow/
│   │   ├── graph.py        # 전체 연결·분기
│   │   ├── state.py        # 공통 실행 상태 형식
│   │   └── checkpoint.py   # 실행 상태 저장·복원
│   ├── features/
│   │   ├── planning/      # 조건 확인·질문·계획 생성
│   │   ├── retrieval/     # 기록 검색·근거 구성
│   │   └── operations/    # 변경 영향 설명·대응안
│   ├── tools/
│   │   ├── records.py     # 기록 검색
│   │   ├── events.py      # 행사 조회
│   │   └── accounting.py  # BE 계산 호출
│   └── clients/
│       └── backend.py     # BE 통신 공통 처리
├── docs/
│   └── architecture.md   # 기능 범위·책임 경계·협업 기준
├── tests/                # 기능 구현 시 테스트 추가
├── AGENTS.md             # AI 작업 규칙
├── .env.example          # 로컬 환경변수 예시
├── .gitignore            # 로컬 설정·캐시·실행 데이터 제외
├── pyproject.toml        # Python 버전·의존성
├── uv.lock               # uv가 생성한 의존성 잠금 파일
└── README.md
```

각 기능 폴더에는 `nodes.py`, `schemas.py`, `prompts/`를 둡니다. 빈 폴더는 `.gitkeep`으로 유지합니다.

## 기능별 담당 범위

| 기능 | 담당 | 예시 |
| --- | --- | --- |
| `planning` | 행사 조건 정리, 부족한 정보 질문, 계획 생성·수정 | 인원 32명·예산 200만 원에 맞춰 행사 단계와 일정 초안 제안 |
| `retrieval` | 과거 기록·회칙 검색, 출처와 근거 구성, 기록 질문 답변 | 작년 MT 회비를 찾아 문서·시트 위치와 함께 반환 |
| `operations` | 운영 중 변경의 영향 설명, 후속 행동과 대응안 제안 | 참가 취소로 최소 인원이 부족해지면 대기자 충원·규모 조정 제안 |

운영 중에도 계획 자체를 다시 만드는 일은 `planning`이 담당합니다. `operations`가 변경 영향과 대응 방향을 정리하면 `workflow`가 필요한 검색·계획 수정을 연결합니다.

## 데이터가 흐르는 경로 (예: 행사 계획 요청)

```text
요청 → api.py → workflow/graph.py
                 → retrieval: 과거 기록과 근거 구성
                 → planning: 조건 확인·질문 또는 계획안 생성
   ← 공통 응답 형식으로 질문·계획안·근거 반환
```

Agent가 도구를 선택해 호출하는 경로에는 `tools/`가 연결됩니다. 실제 분기와 호출 순서는 기능 구현 시 구체화합니다.

## API 연동

BE가 내부 AI API를 호출하는 방향입니다. 구체적인 API 계약과 데이터·실행 책임은 BE와 합의 후 문서화합니다.

공통 요청·응답은 `app/schemas.py`, 기능 전용 형식은 각 기능의 `schemas.py`에서 관리합니다. BE 통신은 `clients/backend.py`에 모읍니다.

## 환경변수

아래는 구현 시 사용할 항목의 초안입니다. 실제 변수 이름과 필수 여부는 설정 코드 작성 시 확정합니다.

| 이름 | 용도 | 상태 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | AI 서비스의 LLM 호출 인증 | 제공자 키 |
| `ANTHROPIC_MODEL` | 사용할 모델 지정 | 변수명·값 확정 예정 |
| `BACKEND_BASE_URL` | AI에서 호출할 BE API 주소 | 변수명·값 확정 예정 |

`.env.example`에는 값의 예시만 기록하고, 실제 키가 든 `.env`는 커밋하지 않습니다. 예시 파일은 작성했으며, 실제 환경변수 로딩은 `config.py` 구현 시 연결합니다.

루트 `.gitignore`에 더해 `ai/.gitignore`에서 AI 전용 제외 규칙을 관리합니다. Python 캐시·가상환경, 로컬 DB, LangGraph 개발 데이터와 로컬 로그·trace 출력은 제외하고 `.env.example`, `uv.lock`, 프롬프트와 소스 코드는 커밋합니다. 향후 실행 결과는 `logs/`, `traces/`, `checkpoints/`, `vectorstore/` 등 지정된 위치에 저장합니다. 이 규칙이 trace나 벡터 저장소의 도입을 의미하지는 않습니다.

## 개발 환경 설치

저장소 루트에서 실행합니다. uv가 필요하며 Python은 3.12 계열을 사용합니다.

```bash
cd ai
uv sync --locked
cp -n .env.example .env
```

`.env`의 API 키·모델 ID·BE 주소를 로컬 환경에 맞게 설정하세요. 기존 `.env`는 덮어쓰지 않습니다.

최소 의존성은 FastAPI, Uvicorn, LangGraph, Anthropic 연동용 `langchain-anthropic`, BE 통신용 HTTPX, 스키마·설정용 Pydantic과 pydantic-settings입니다. LangChain 전체 패키지는 직접 추가하지 않았습니다. 의존성 변경 시 `uv add`/`uv remove`를 사용하고 `pyproject.toml`과 `uv.lock`을 함께 커밋합니다.

현재는 의존성 설치만 가능하며 FastAPI 앱과 설정 로딩이 구현되지 않아 서버 실행 명령은 제공하지 않습니다. Dockerfile은 실행 코드 작성 시 추가합니다. Trace와 evaluation은 이번 구성에 포함하지 않습니다.

작업 규칙은 [AGENTS.md](AGENTS.md), 기능별 구조와 설계안은 [AI 아키텍처 문서](docs/architecture.md)를 참고하세요. 아키텍처 문서의 BE 관련 책임 분담은 협의 전 설계안입니다.
