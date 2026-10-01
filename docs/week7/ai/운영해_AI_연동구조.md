# 운영해 · AI 연동 구조

> 작성 기준: 2026-09-23
>
> AI 모듈의 현재 구조와 이번 주에 구현한 연동 기반을 정리한다.

---

## 전체 구조

AI는 별도 서버가 아니라 `be/app/ai/` 안에서 동작하는 BE 내부 모듈이다.

```text
FE ──REST──▶ BE Router / Service
                  │
                  ▼
             app.ai 공개 경계
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   LLM·임베딩 호출      ports를 통한
                       BE 조회·계산
```

- BE는 `app.ai`에 공개된 기능만 호출한다.
- AI는 BE의 ORM·DB·서비스를 직접 참조하지 않고 `ports.py`를 사용한다.
- AI는 조건·계획·대응안을 제안하고, 저장·권한·승인·실행·정확한 계산은 BE가 담당한다.

---

## 이번 주 작업

### 1. 채팅 모델 연동

- `AISettings`로 모델 주소·키·모델명·타임아웃을 관리한다.
- API 키는 `SecretStr`로 보관해 로그나 테스트 출력에 노출되지 않게 했다.
- 설정은 import 시점이 아니라 모델을 만들 때 검증한다.
- Tool 호출을 지원하기 위해 Responses API 경로를 사용한다.
- 공통 모델은 `llm.py`에서 생성하고 재사용한다.

### 2. 임베딩 기반

- `text-embedding-3-small`을 사용하며 출력은 1536차원이다.
- 채팅 모델과 임베딩의 API 주소를 따로 관리한다.
- 임베딩 키를 비우면 채팅 모델의 API 키를 재사용한다.
- RAG 저장소는 PostgreSQL pgvector를 사용하고 벡터 컬럼은 `vector(1536)`으로 두는 방향이다.

임베딩 연결·배치 호출·차원은 실제 API로 확인했다. 청킹 방법과 검색 로직은 아직 구현하지 않았다.

### 3. BE-AI planning 계약 (develop 반영 예정)

`contracts.py`에 행사 계획 대화와 계획안 생성에 필요한 입·출력 타입을 정의했다.
현재 planning 계약 작업 브랜치에서 검증을 마쳤으며 develop 반영을 앞두고 있다.

```text
BE가 Event·Message 조회
  → PlanChatRequest로 AI 호출
  → PlanChatResult 또는 PlanDraft 반환
  → BE가 검증·저장
```

계약에서 대화 누락, 빈 답변, 단계가 없는 계획안, 정의되지 않은 필드 추가 등을 잘못된 결과로 간주해 경계에서 거부한다. Step·Action ID, 상태, 승인 여부는 BE가 결정하므로 AI 계약에 담지 않는다.

---

## 오류 처리 (develop 반영 예정)

AI 오류는 재시도 가능 여부로 구분한다.

| 구분 | 의미 |
| --- | --- |
| `AIConfigError` | 설정을 고치기 전에는 재시도해도 실패 |
| `AIRetryableError` | 같은 생성 요청을 다시 시도할 수 있는 실패 |
| `AITimeoutError` | 모델 응답 시간 초과 |
| `AIInvalidResponseError` | 모델 응답이 예상한 계약을 만족하지 못함 |

HTTP 상태와 FE 에러 코드로 변환하는 일은 BE 연동 구현에서 정한다.

---

## 검증

현재 develop에서 AI 모듈 테스트 28건이 통과했다.
planning 계약 작업 브랜치에서는 계약·오류 테스트를 포함해 42건이 통과했다.

```text
develop: 28 passed
planning 계약 작업 브랜치: 42 passed
```

설정·비밀값 보호·모델 생성·임베딩 구성·계약 검증·오류 분류를 테스트한다. 실제 ML API 점검은 키가 필요해 수동 스크립트로 실행한다.

---

## 아직 구현하지 않은 범위

- `facade.py`의 실제 planning 공개 함수
- `ports.py`와 BE 조회·계산 구현체 연결
- 계획 대화·계획안 생성 프롬프트와 workflow
- RAG 청킹·색인·검색
- Router부터 AI 호출·DB 저장까지의 통합 검증

---

## 관련 문서

- [AI 기능 요구사항](../../../be/app/ai/docs/requirements.md)
- [AI 아키텍처](../../../be/app/ai/docs/architecture.md)
- [BE-AI 데이터 계약](../../../be/app/ai/docs/contracts.md)
- [AI 모듈 README](../../../be/app/ai/README.md)
