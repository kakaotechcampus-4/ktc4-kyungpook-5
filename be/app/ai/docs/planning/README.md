# 행사계획 개발 안내

현재 공개 P1은 `agent/`, `generation/`, `public_workflow.py`, `state_codec.py`를 사용한다. 이전 조건 추출 → 검색 판단 → 규칙 질문 → 답변 조립 구현은 [코드 legacy 안내](../../features/planning/legacy/README.md)로 분리했다. 이전 테스트 API와 평가 스크립트는 보존하지만 현재 공개 P1에서는 호출하지 않는다.

BE/FE 연결은 [P1 전달 안내](p1-handoff.md)를 먼저 읽는다. 공개 함수 호출, 실제 응답, 저장/실패 처리와 UI 사진을 정리했다. 상세 타입과 책임은 [P1 공개 계약](p1-public-contract.md), 공동 합의는 [#179](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/179)에서 확인한다.

생성 권유 수락 후 반복 실패하는 사례는 [출력·전송 한도 진단(#176)](evaluation.md)에서 원인·전후 실측·재실행을 확인한다. 생성 호출만 스트리밍과 명시적 출력 한도를 사용하며, UI는 검증된 완성본을 계속 한 번에 받는다.

LLM이 사용자와 대화하고 필요한 Tool을 선택하는 행사계획 기능을 여기서 관리한다.

1. [전체 설계](design.md): 어떤 대화 경험과 Node·Tool 구조를 만드는가.
2. [코드 따라가기](walkthrough.md): 입력 → 핵심 코드 → 결과를 단계별로 읽는다.
3. [1단계 명세](step-01-state-tool.md): 행사 초안과 조건 변경 Tool의 계약.
4. [2단계 명세](step-02-agent-graph.md): LLM의 Tool 선택·대화와 LangGraph 연결.
5. [3단계 UI 연결](step-03-ui.md): 실행 주소·상담/잠정 반영·오류/재시도·BE/FE 합의 항목.
6. [4단계 검색 Tool](step-04-record-tool.md): 기존 검색 재사용·출처 표시·검색 결과 수락 흐름.
7. [새 Agent 검증 기록](evaluation.md): 실제 대화의 조건·Tool 선택과 답변 관찰.
8. [Legacy 안내](legacy/README.md): 기존 구현·평가·UI 실행 방법.
9. [5단계 생성 권유·P2 전달 명세](step-05-generation.md): 먼저 권유하기·수락/보류·별도 생성 graph, 채팅/버튼 HTTP와 읽기 전용 P2 연결.

작업 순서는 1) 초안 State·조건 변경 Tool → 2) 실제 LLM·LangGraph → 3) UI 연결 → 4) 기록 검색 Tool → 5) 계획 생성이다. [테스트 화면](http://127.0.0.1:5174/)에서 저장 없이 대화·검색·계획 초안 생성을 실행할 수 있다. 공개 BE 연동·저장·계획 수정·검색 품질 개선은 후속 범위다. 관련 #165~#169 / AI-PLAN-01~04.

5-1 명세(#171)·5-2 내부 생성 Tool/graph(#172)·5-3 로컬 P2 연결(#173)을 구현했다. 채팅의 생성 Tool과 버튼의 별도 함수가 같은 생성 graph를 쓴다. 생성 가능 조건과 LLM의 권유 타이밍을 구분하며, 사용자 요청·수락·클릭으로 초안을 만든다. 실제 모델과 UI에서 두 경로를 확인했고, 자발적 권유·JSON 출력의 남은 제한은 [평가 기록](evaluation.md)에 있다. 관련 AI-PLAN-02·05.

테스트 UI는 [tests/ui/planning](../../tests/ui/planning/README.md)의 독립 앱으로 관리한다(#174). 제품 `fe/`를 수정·참조하지 않으며, FE팀에는 동작 예시·계약·요청 사항을 전달한다. 실행 주소는 `http://127.0.0.1:5174/`이며 기존 제품 FE의 `/dev/planning` 경로는 제거했다.
