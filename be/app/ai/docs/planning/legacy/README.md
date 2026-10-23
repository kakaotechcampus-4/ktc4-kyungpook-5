# 이전 행사계획 구현 — 참고용

고정된 조건 추출 → 조회 판단 → 질문·답변 조립 방식의 문서와 평가를 보관한다. 새 개발은 [planning 안내](../README.md)에서 시작한다.

- [기존 상세 설계](plan_architecture.md), [코드 따라가기](planning-walkthrough.md)
- [평가 기록](planning-evaluation.md), [과거 이슈 초안](planning-issue-drafts.md), [단계 카탈로그](step-catalog.md)
- [기존 UI 실행 방법](planning-ui-test.md), `evaluation-results/`, `ui-tests/`

실행 코드도 아직 남아 있다. `features/planning/`의 `nodes.py`, `lookup.py`, `questions.py`, `turn_flow.py`, `turn_assembly.py`, `turn_schemas.py`, `turn_policy.py`와 기존 추출·조회 프롬프트가 legacy 대화 경로다. 테스트 UI와 과거 평가 스크립트가 호출하므로 이번 문서 정리에서 이동·삭제하지 않는다.

`schemas.py`의 조건 값·필드별 타입과 `records.py`의 검색 연결은 재사용 대상으로 구분한다. 새 구현은 `features/planning/agent/`에 둔다. 기존 질문 순서를 강제하는 테스트를 새 Agent의 요구사항으로 자동 채택하지 않는다. 여기의 평가는 당시 구현의 관측값이며 새 Agent의 성능 수치가 아니다.
