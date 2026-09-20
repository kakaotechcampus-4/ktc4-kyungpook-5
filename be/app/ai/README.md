# 운영해 · AI 모듈

AI 팀이 담당하는 BE 내부 모듈입니다. 
행사 계획·수정, 과거 기록 검색, 운영 중 변경에 대한 대응안 제안을 담당합니다.

## 관련 문서

- [기능 요구사항](docs/requirements.md): 제공할 사용자 경험과 확인 기준
- [아키텍처](docs/architecture.md): 기능별 역할과 AI·BE 책임 경계
- [작업 규칙](AGENTS.md): 요구사항 → Issue → 구현 → PR 협업 절차
- [이전 기록](docs/migration.md): 모듈 이전 내역과 BE 팀 후속 작업

## 구조

```text
be/app/ai/
├── __init__.py          # BE가 import하는 단일 공개 경계: app.ai
├── facade.py            # BE가 호출할 AI 기능의 구현 위치
├── contracts.py         # 합의 후 정의할 공개 요청·응답 데이터
├── ports.py             # AI가 사용할 BE 조회·계산 인터페이스
├── config.py            # AI 전용 설정
├── errors.py            # AI 내부 오류 타입
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
│   ├── requirements.md  # 사용자 경험 중심 AI 기능 요구사항 초안
│   ├── migration.md     # 파일 대응표·BE 팀 후속 작업
│   └── legacy-dependencies/ # 이전 서비스 의존성 원본, 설치 대상 아님
├── AGENTS.md
├── CLAUDE.md            # AGENTS.md를 참조하는 Claude 진입점
├── .env.example         # 공통 환경변수에 합칠 항목의 참고 자료
└── .gitignore
```

각 기능에는 `nodes.py`, `schemas.py`, `prompts/`를 둡니다.

## 연동 규칙

- BE는 `app.ai`에 공개된 기능과 타입만 사용합니다.
- AI는 `ports.py`를 통해 주입받은 BE 기능을 사용하며, BE 서비스·ORM·DB를 직접 참조하지 않습니다.
- AI는 계획과 대응안을 제안합니다. 권한·승인 검증·저장·확정 실행은 BE가 담당합니다.
- BE와 AI는 같은 프로세스에서 함수로 호출합니다. 별도 AI 서버는 두지 않습니다.


## 개발 환경과 설정

사용 기술은 Python 3.12, LangGraph, langchain-openai, Pydantic, pydantic-settings입니다.
모델 연동은 Elice ML API의 OpenAI 호환 API와 `ChatOpenAI`를 기준으로 합니다.

환경변수는 다음 항목을 사용하도록 구성합니다.

| 변수 | 용도 |
| --- | --- |
| `AI_API_BASE_URL` | 모델 API 기본 주소 |
| `AI_API_KEY` | 모델 API 인증 키 |
| `AI_MODEL` | 사용할 모델 |
| `AI_REQUEST_TIMEOUT_SECONDS` | 모델 요청 제한 시간 |

설정은 BE 실행 환경에서 전달하며 AI 모듈 전용 `.env`는 자동 로드하지 않습니다.
의존성 설치와 실행은 BE에서 통합 관리합니다.
