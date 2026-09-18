# 운영해 · AI 모듈

AI 팀 2명이 담당하는 BE 내부 모듈입니다. 행사 계획·수정, 과거 기록 검색,
운영 중 변경에 대한 대응안 제안을 담당합니다.

이슈 #18에서 독립 서비스 구조를 `be/app/ai/`로 이전했습니다.
현재 Python 파일은 역할 설명 수준의 스텁입니다. 업무 함수·요청/응답 타입·
LangGraph 실행·설정 로딩은 아직 구현되지 않았으며 서버를 실행할 수 없습니다.
**모듈 이전 완료와 단일 서비스 실행 완료는 구분합니다.**

## 구조

```text
be/app/ai/
├── __init__.py          # BE가 import하는 단일 공개 경계: app.ai
├── facade.py            # BE가 호출할 AI 기능의 구현 위치
├── contracts.py         # 합의 후 정의할 공개 요청·응답 데이터
├── ports.py             # AI가 사용할 BE 조회·계산 인터페이스
├── config.py            # AI 전용 설정
├── llm.py               # 공통 모델 구성
├── features/
│   ├── planning/        # 조건 확인·질문·계획 생성 및 수정
│   ├── retrieval/       # 기록 검색·근거 구성
│   └── operations/      # 변경 영향 설명·대응안
├── workflow/            # 기능 연결·분기·실행 상태
├── tools/               # Agent 도구, BE 기능은 주입된 port로 호출
├── tests/               # AI 테스트 위치 (현재 빈 폴더)
├── docs/
│   ├── architecture.md
│   ├── migration.md     # 파일 대응표·BE 팀 후속 작업
│   └── legacy-dependencies/ # 이전 서비스 의존성 원본, 설치 대상 아님
├── AGENTS.md
├── .env.example         # 공통 환경변수에 합칠 항목의 참고 자료
└── .gitignore
```

각 기능에는 `nodes.py`, `schemas.py`, `prompts/`를 둡니다.

## 호출 경계

BE는 `app.ai`에서 공개한 이름만 사용합니다. 합의된 facade·계약·port는
`__init__.py`에서 명시적으로 재공개합니다. 현재 공개 업무 API는 없습니다.
BE가 `features/`, `workflow/`, `tools/` 또는 facade 내부를 직접 import하지 않습니다.

AI는 BE의 ORM 모델·DB 세션·서비스를 직접 import하지 않습니다.
필요한 BE 기능은 `ports.py`에 계약을 정의한 뒤 BE 측에서 구현체를 주입합니다.
ORM 객체나 HTTP 응답 객체 대신 합의된 데이터 형식을 전달합니다.
함수명·필드·타임아웃·오류 규약은 BE와 합의 후 구현합니다.

```text
BE 서비스 → app.ai 공개 기능 → facade → workflow → features
AI tools → 주입된 port → BE 조회·계산 구현
```

같은 프로세스의 함수 호출을 사용하며 별도 AI FastAPI 앱과 내부 HTTP 통신은 없습니다.
HTTP 라우팅·인증·승인 검증·확정 변경 실행은 BE가 담당합니다.

## 구현 원칙

- 기능 내부 처리는 features, 기능 간 연결은 workflow에 둡니다.
- 회계 계산은 BE의 결정론적 코드가 담당하며 AI는 결과를 보정하지 않습니다.
- 기록 기반 답변에는 출처·원문 위치를 포함하고 사실과 가정을 구분합니다.
- Agent와 Tool은 역할을 구분하며 기능 폴더가 Agent 하나를 의미하지 않습니다.

## 의존성과 실행 환경

Python 3.12, LangGraph, langchain-anthropic, Pydantic, pydantic-settings를 사용합니다.
모델·버전 선택과 실제 설정 로딩은 미확정입니다.
FastAPI 앱과 최종 의존성은 BE 팀이 통합합니다.

이전 `pyproject.toml`과 `uv.lock`은
`docs/legacy-dependencies/`에 원본 그대로 보관합니다.
독립 프로젝트 실행·설치 용도가 아니며 해당 폴더에서 `uv sync`를 실행하지 않습니다.
BE 통합 후 의존성의 단일 기준은 `be/pyproject.toml`과 `be/uv.lock`이 됩니다.
현재 BE 의존성 파일은 수정하지 않았으며 통합 설치·실행 명령은 아직 없습니다.

환경변수 참고 항목은 `.env.example`의 `ANTHROPIC_API_KEY`,
`ANTHROPIC_MODEL`입니다. 모듈 전용 .env를 자동 로드하지 않습니다.
`BACKEND_BASE_URL`은 내부 함수 호출에 필요하지 않습니다.

## 후속 작업

BE 팀의 의존성·초기화·주입 작업과 기존 공용 문서의 후속 수정은
[이전 기록](docs/migration.md)을 참고하세요.
SSE, 승인 interrupt, 체크포인트 저장소, 배포 통합은 이번 범위에 포함하지 않습니다.
답변 토큰 스트리밍은 사용하지 않는 방향이며 단계 이벤트는 후속 설계 대상입니다.

[작업 규칙](AGENTS.md) · [아키텍처](docs/architecture.md)
