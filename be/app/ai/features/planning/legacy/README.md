# 이전 행사계획 흐름 (Legacy)

현재 `app.ai.chat_planning`과 `generate_planning_preview`에서 호출하지 않는 이전 설계다. 동작 비교와 기존 평가 재현을 위해 보존한다.

```text
process_planning_turn
  → nodes: 조건 변경 추출/검증
  → lookup: 검색/생략/확인 판단
  → records: 공통 retrieval 검색
  → questions: 규칙에 따른 다음 질문
  → turn_assembly: 답변과 상태 조립
```

- `turn_flow.py`: 전체 순서를 연결한다.
- `turn_schemas.py`, `schemas.py`: 이전 흐름의 데이터 계약이다.
- `turn_policy.py`: 이전 생성 가능 판정이다. 현재 기준은 `../generation/readiness.py`다.
- `prompts/`: 이전 조건 추출과 검색 판단 프롬프트다.
- 현재 Agent도 사용하는 조건 값/발화 타입은 `../schemas.py`, 공개 계약은 루트 `contracts.py`에 있다.

호출 경로는 유지한다.

- 로컬 테스트 서버의 `POST /__planning-test/turn`
- `scripts/eval_planning_turns.py`, `eval_planning_conditions.py`, `check_planning_questions.py`
- 이전 흐름의 회귀 테스트

현재 테스트 화면은 `/__planning-test/agent/turn`과 `/__planning-test/agent/generate`를 사용한다. 이전 API를 제품 연결에 사용하지 않는다.

이전 내부 Python import 경로는 `app.ai.features.planning.legacy.*`로 바뀌었다. 저장소 안의 사용처를 갱신했고 공개 `app.ai` 이름과 HTTP 경로, 입력/출력 의미는 바꾸지 않았다. 저장소 밖에서 이전 내부 경로를 직접 사용했다면 import를 갱신해야 한다.
