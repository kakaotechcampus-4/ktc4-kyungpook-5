# 행사계획 개발 안내

LLM이 사용자와 대화하고 필요한 Tool을 선택하는 행사계획 기능을 여기서 관리한다.

1. [전체 설계](design.md): 어떤 대화 경험과 Node·Tool 구조를 만드는가.
2. [코드 따라가기](walkthrough.md): 입력 → 핵심 코드 → 결과를 단계별로 읽는다.
3. [1단계 명세](step-01-state-tool.md): 행사 초안과 조건 변경 Tool의 계약.
4. [2단계 명세](step-02-agent-graph.md): LLM의 Tool 선택·대화와 LangGraph 연결.
5. [3단계 UI 연결](step-03-ui.md): 실행 주소·상담/잠정 반영·오류/재시도·BE/FE 합의 항목.
6. [새 Agent 검증 기록](evaluation.md): 실제 대화의 조건·Tool 선택과 답변 관찰.
7. [Legacy 안내](legacy/README.md): 기존 구현·평가·UI 실행 방법.

작업 순서는 1) 초안 State·조건 변경 Tool → 2) 실제 LLM·LangGraph → 3) UI 연결 → 4) 기록 검색 Tool이다. 1~3단계를 내부 구현했다. [테스트 화면](http://127.0.0.1:5173/dev/planning)은 새 Agent를 호출하며 저장 없이 대화할 수 있다. 검색 Tool과 P2는 후속 범위다. 관련 #165~#168 / AI-PLAN-01~04.
