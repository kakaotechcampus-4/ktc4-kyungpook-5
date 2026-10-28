# 운영해 · AI 모듈

> **현재 행사계획:** `app.ai.chat_planning`과 `generate_planning_preview`로 조건 대화와 최초 계획 생성을 호출할 수 있습니다. 공개 요청/결과 타입과 JSON 상태 변환도 구현했습니다. 실제 제품의 DB 저장, HTTP, FE 연결은 [#187](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/187)에서 진행할 범위입니다. [P1 전달 안내](docs/planning/p1-handoff.md) → [공개 계약](docs/planning/p1-public-contract.md) → [코드 따라가기](docs/planning/walkthrough.md) 순서로 읽습니다.

AI 팀이 담당하는 BE 내부 모듈입니다. 
행사 계획·수정, 과거 기록 검색, 운영 중 변경에 대한 대응안 제안, 회의 중 기록 조회를 담당합니다.

## 관련 문서

- [행사계획 개발 안내](docs/planning/README.md): 새 설계·단계별 명세·코드 흐름과 legacy 자료의 진입점

- [행사계획 코드 따라가기](docs/planning/walkthrough.md): 처음/오랜만에 읽을 때 보는 흐름 → 코드 → 입력·출력 예시 안내
- [기능 요구사항](docs/requirements.md): 제공할 사용자 경험과 확인 기준
- [아키텍처](docs/architecture.md): 기능별 역할과 AI·BE 책임 경계
- [행사계획 설계](docs/planning/design.md): 현재 Agent의 상태, Node, Tool과 생성 흐름
- [행사계획 평가](docs/planning/evaluation.md): 실제 모델 검증과 생성 실패 진단, 미검증 범위
- [Legacy 안내](docs/planning/legacy/README.md): 이전 고정 추출과 질문 방식의 문서 및 평가
- [BE-AI 데이터 계약](docs/contracts.md): 계약의 목적, 계획 대화·기록 색인 연동 예시, 회의 발화 처리 초안
- [AI 오류 타입](docs/errors.md): 오류 분류와 모델 호출 오류 변환 기준
- [기록 색인·검색 평가 기록](docs/retrieval-evaluation.md): 청킹·임베딩 측정값과 관찰
- [회의 어시스턴트 측정 기록](docs/meeting-evaluation.md): 판단 모델·Whisper·지연 측정값과 관찰
- [계획 단계 카탈로그](docs/planning/legacy/step-catalog.md): 계획안의 단계·행동 기준 목록
- [작업 규칙](AGENTS.md): 요구사항 → Issue → 구현 → PR 협업 절차
- [이전 기록](docs/migration.md): 모듈 이전 내역과 BE 팀 후속 작업

## 구조

| 영역 | 현재 상태 |
| --- | --- |
| P1 조건 대화 | `agent/`의 LangGraph가 상담하거나 조건 변경, 기록 검색, 생성 권유 Tool을 선택 |
| 최초 계획 생성 | 채팅의 생성 Tool과 버튼 함수가 `generation/`의 공통 생성 Graph 사용 |
| 공개 경계 | 루트 `contracts.py`, `facade.py`와 `public_workflow.py`에 구현 |
| 상태 이어가기 | `state_codec.py`가 대화와 Tool 이력, 권유, 마지막 초안을 JSON으로 변환하고 복원 |
| 제품 연결 | BE의 권한 검사, 실제 검색 port, DB 저장, 요청 중복과 버전 검사, HTTP 및 FE 연결 필요 |
| P2 편집과 AI 검토 | [#177](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/177)에서 협의 중이며 AI 검토 미구현 |
| 운영 Agent | 전체 신호 대기와 운영 흐름은 설계 단계 |

P1은 행사 조건 대화와 최초 생성 요청까지입니다. 단계 제외와 복원, 순서 변경은 P2 범위입니다. 테스트 UI는 `tests/ui/planning/`의 독립 앱이고 제품 `fe/`를 수정하거나 참조하지 않습니다. 이전 고정 추출과 질문 조립 코드는 `features/planning/legacy/`에 보존하며 현재 공개 P1에서 호출하지 않습니다.

현재 이력 한도는 Tool 메시지 포함 60개이며 자동 압축은 없습니다. 한도 안내 정보는 #194, 압축 설계는 #195의 후속 작업입니다. #196의 [응답 시간 기준](docs/planning/latency-baseline.md)에 맞춰 고정 입력과 반복 실행기, 전체/세부 구간 관측과 오프라인 집계를 구현했습니다. 실제 모델 기준값 수집은 아직 진행하지 않았습니다. 검증의 표본과 한계는 평가 기록을 확인합니다.

```text
be/app/ai/
├── __init__.py          # BE가 import하는 단일 공개 경계: app.ai
├── facade.py            # BE가 호출할 AI 기능의 구현 위치
├── contracts.py         # BE와 주고받는 요청·응답 데이터
├── ports.py             # AI가 사용할 BE 조회·계산·기록 검색 인터페이스
├── config.py            # AI 전용 설정
├── errors.py            # AI 내부 오류 타입
├── llm.py               # 공통 채팅·임베딩 모델 생성
├── features/
│   ├── planning/        # agent, generation, 공개 실행/상태 변환, legacy (P2 수정 후 검토는 미구현)
│   ├── retrieval/       # 기록 색인·검색·근거 구성 (chunking: 청킹, indexing: 색인, nodes: 기록 검색 search_records, memory_port: 개발용 검색 구현)
│   ├── operations/      # 변경 영향 설명·대응안
│   └── meeting/         # 회의 발화 판단과 답 (context: 판단 입력, nodes: 판단·결과 구성, lookup: 기록 검색 연결과 카드 문구, questions: 판단 전용 모델의 질문)
├── workflow/            # 행사 Agent 실행 흐름·분기·실행 상태
├── tools/               # Agent 도구, BE 기능은 주입된 port로 호출
├── scripts/             # 실제 모델 확인·측정 스크립트 (CI 제외. 대부분 키 필요, Laya는 uv run --with로 잴 때만 붙임)
├── tests/               # AI 테스트 (fixtures/records: 예시 기록, fixtures/eval: 기록 검색 평가 질문·회의 판단 평가 문항·평가 세트, ui/planning: 독립 계획 테스트 UI)
├── docs/
│   ├── architecture.md
│   ├── contracts.md     # BE-AI 데이터 계약 설명
│   ├── errors.md        # AI 오류 타입과 변환 기준
│   ├── retrieval-evaluation.md # 기록 색인·검색 측정 기록
│   ├── meeting-evaluation.md # 회의 판단·음성 인식·지연 측정 기록
│   ├── requirements.md  # 사용자 경험 중심 AI 기능 요구사항 초안
│   ├── planning/        # 새 설계·단계별 명세·코드 안내, legacy/에 이전 자료 보관
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
- 전체 설계는 행사별 Agent 하나가 신호를 기다리는 방식입니다. 현재 구현은 P1 요청 처리와 상태 반환까지이며 상시 대기 및 운영 신호 연결은 후속 범위입니다.
- BE와 AI는 같은 프로세스에서 함수로 호출합니다. 별도 AI 서버는 두지 않습니다.


## 개발 환경과 설정

사용 기술은 Python 3.12, LangGraph, langchain-openai, Pydantic, pydantic-settings입니다.
모델 연동은 Elice ML API의 OpenAI 호환 API와 `ChatOpenAI`를 기준으로 합니다.
채팅 모델은 `gpt-5.6-luna`이며 모델명은 `AI_MODEL`로 전달합니다. 회의 판단도 이 모델을 씁니다.
게이트웨이는 모델마다 배포 주소가 달라서, 모델을 바꾸면 `AI_API_BASE_URL`도 그 모델의 주소로 바꿉니다.

임베딩은 `openai/text-embedding-3-small`을 같은 게이트웨이의 별도 배포로 호출합니다.
출력은 1536차원이고 이 값이 저장소(pgvector) 컬럼 차원을 정합니다.

모델은 `llm.py`에서만 만듭니다. 기본 구성은 `get_chat_model()`,
기능별 조정이 필요하면 `build_chat_model()`을 사용합니다.
임베딩은 `get_embeddings()`와 `build_embeddings()`를 사용합니다.
`gpt-5` 계열은 `temperature=1` 외의 값을 받지 않으므로 답변을 일정하게
유지할 때는 온도 대신 프롬프트와 구조화 출력을 사용합니다.

구조화 출력은 `await ainvoke_structured(messages, Schema)`로, 임베딩은 `await aembed_texts(texts)`로 호출합니다.
실패하면 AI 오류 타입으로 올라오며, 변환 기준은 [AI 오류 타입](docs/errors.md)을 따릅니다.

호출 경로는 Responses API(`/v1/responses`)로 고정합니다.
`gpt-5.6-terra`는 `/v1/chat/completions`에서 function tools를 거부하므로
Agent가 Tool을 사용하려면 이 경로여야 합니다.
이 경로에서는 응답 `content`가 문자열이 아니라 블록 목록으로 오므로
본문만 필요하면 `response.text`를 사용합니다.

추론 깊이는 호출별로 정합니다. 기본값은 낮추지 않고, 판단이 필요 없는 단순한
Agent·노드에서만 `build_chat_model(reasoning={"effort": "none"})`으로 줄입니다.
`none`은 추론을 끄고 나머지 값은 추론을 사용합니다.

환경변수는 다음 항목을 사용하도록 구성합니다.

| 변수 | 용도 |
| --- | --- |
| `AI_API_BASE_URL` | 모델 API 기본 주소 |
| `AI_API_KEY` | 모델 API 인증 키 |
| `AI_MODEL` | 사용할 모델 |
| `AI_REQUEST_TIMEOUT_SECONDS` | 모델 요청 제한 시간 |
| `AI_EMBEDDING_BASE_URL` | 임베딩 API 기본 주소. 채팅과 다른 배포입니다 |
| `AI_EMBEDDING_API_KEY` | 임베딩 API 인증 키. 비우면 `AI_API_KEY`를 씁니다 |
| `AI_EMBEDDING_MODEL` | 사용할 임베딩 모델 |

설정은 BE 실행 환경에서 전달하며 AI 모듈 전용 `.env`는 자동 로드하지 않습니다.
의존성 설치와 실행은 BE에서 통합 관리합니다.
