# 이슈 #18 · AI 모듈 이전과 BE 인계

## 현재 완료 범위

기존 AI 구조를 `be/app/ai/`로 이전하고 단일 공개 경계의 위치를 정의했습니다.
업무 API·타입·Agent·DB·설정 로딩은 구현하지 않았습니다.
기존 BE 파일, FE, 루트 공용 설정은 수정하지 않았습니다.

## 파일 대응표

| 이전 | 이후 | 처리 |
| --- | --- | --- |
| ai/app/features, workflow, tools | be/app/ai/ 아래 동일 폴더 | 역할별 구조 유지 |
| ai/app/config.py, llm.py | be/app/ai/ 아래 동일 파일 | 모듈 설정·모델 위치 |
| ai/app/api.py | be/app/ai/facade.py | HTTP API 대신 공개 기능 구현 위치 |
| ai/app/schemas.py | be/app/ai/contracts.py | 공개 요청·응답 계약 위치 |
| ai/app/clients/backend.py | be/app/ai/ports.py | HTTP 대신 주입할 BE 기능 계약 위치 |
| ai/app/main.py | 제거 | 독립 FastAPI 앱 불필요 |
| 없음 | be/app/ai/__init__.py | BE가 사용하는 단일 공개 진입점 |
| ai/README.md, AGENTS.md, docs/architecture.md | be/app/ai/ 아래 동일 상대 경로 | 설명·작업 범위 갱신 |
| ai/tests | be/app/ai/tests | AI 소유 영역에서 테스트 유지 |
| ai/.gitignore, .env.example | be/app/ai/ 아래 동일 파일 | 제외 규칙 보존, BE URL 항목 제거 |
| ai/pyproject.toml, uv.lock | be/app/ai/docs/legacy-dependencies/ | 이전 명세 원본 보존 |

Git은 커밋 비교 시 내용 유사성으로 이동을 감지합니다.
`legacy-dependencies`는 원본 보관용이며 설치·실행 루트가 아닙니다.
그 안의 `readme = "README.md"` 등은 이전 프로젝트 기준 원본 값입니다.

## BE 팀 후속 작업

- [ ] Python 3.12 기준으로 통합 pyproject.toml을 구성하고 uv.lock을 생성한다.
- [ ] LangGraph, langchain-openai, Pydantic, pydantic-settings의 필요 버전을 검토한다.
      모델 호출이 OpenAI 호환 게이트웨이로 정해져 langchain-anthropic은 사용하지 않는다.
- [ ] 기존 FastAPI·Uvicorn은 BE 실행 의존성으로 관리한다.
- [ ] HTTPX는 BE↔AI 내부 호출용이 아니다. ML API 호출은 langchain-openai가
      함께 설치하는 openai 클라이언트를 사용하므로 직접 의존성 필요 여부만 확인한다.
- [ ] AI_API_BASE_URL·AI_API_KEY·AI_MODEL을 공통 설정에 연결한다.
      ML API 키를 사용하므로 ANTHROPIC_API_KEY·ANTHROPIC_MODEL은 쓰지 않는다.
- [ ] AI_SERVICE_BASE_URL·BACKEND_BASE_URL의 별도 서비스 전제를 제거한다.
- [ ] BE 조회·계산 구현체를 합의된 AI port에 연결하고 AI 객체를 초기화한다.
- [ ] BE 서비스는 app.ai에서 공개된 이름만 사용한다.
- [ ] 앱 초기화·DB 세션 수명·오류 변환·통합 실행 검증을 수행한다.

이번 작업에서는 BE의 `infra/agent_client.py`도 그대로 둡니다.
후속 통합 시 BE 팀이 내부 함수 호출에 맞게 정리해야 합니다.
기존 BE README의 AI 서버·설치 안내도 후속 수정 대상입니다.

## 공동 합의가 필요한 계약

- 공개 기능의 함수명, 입력·출력 필드와 오류 형식
- BE 조회·계산 port의 메서드와 구현체 주입 방식
- 비동기 호출, 타임아웃, 트랜잭션과 리소스 수명
- 행사 원본 상태·승인 데이터와 AI 실행 상태의 책임 경계

합의 전 빈 Protocol·임의 DTO·가짜 정상 응답을 만들지 않습니다.
공개 업무 계약이 없으므로 현재 `app.ai.__all__`은 비어 있습니다.
Python import 자체가 내부 접근을 강제로 차단하지는 않습니다.
실제 계약 구현 시 공개 import 목록과 의존 경계를 리뷰·검사합니다.

## 공용 문서·설정 후속 수정

`docs/tech-stack.md`, `be/README.md`에는 이전 별도 서비스 설명이 남아 있습니다.
이번 이슈의 변경 경계를 지키기 위해 수정하지 않았으며 통합 시 갱신해야 합니다.
`.github/CODEOWNERS`와 AI 경로 기반 자동화·라벨 설명도 소유권 담당자가
새 경로에 맞춰 검토해야 합니다. BE 전체 규칙과 AI 하위 규칙의 우선순위를 확인합니다.

## 제외 범위와 완료 판단

SSE, 승인 interrupt, 체크포인트 저장소, 기능 구현, 배포 통합은 후속 작업입니다.
이 이슈의 완료는 모듈 위치·경계·인계 문서 정리이며 서버 기동 완료가 아닙니다.
통합 의존성 명세가 확정되기 전까지 원본 의존성 자료를 유지합니다.
