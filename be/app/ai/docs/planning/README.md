# 행사계획 개발 안내

LLM이 사용자와 대화하고 필요한 Tool을 선택하는 행사계획 기능을 여기서 관리한다.

1. [전체 설계](design.md): 어떤 대화 경험과 Node·Tool 구조를 만드는가.
2. [코드 따라가기](walkthrough.md): 입력 → 핵심 코드 → 결과를 단계별로 읽는다.
3. [1단계 명세](step-01-state-tool.md): 행사 초안과 조건 변경 Tool의 계약.
4. [2단계 명세](step-02-agent-graph.md): LLM의 Tool 선택·대화와 LangGraph 연결.
5. [새 Agent 검증 기록](evaluation.md): 실제 대화의 조건·Tool 선택과 답변 관찰.
6. [Legacy 안내](legacy/README.md): 기존 구현·평가·UI 실행 방법.

작업 순서는 1) 초안 State·조건 변경 Tool → 2) 실제 LLM·LangGraph → 3) UI 연결 → 4) 기록 검색 Tool이다. 1·2단계의 처리기·그래프를 구현했고 실제 모델의 합성 대화 10턴을 확인했다. 현재 UI는 legacy를 호출하며 새 흐름 연결은 3단계다. 관련 #165~#167 / AI-PLAN-01~04.
