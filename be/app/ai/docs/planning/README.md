# 행사계획 개발 안내

LLM이 사용자와 대화하고 필요한 Tool을 선택하는 행사계획 기능을 여기서 관리한다.

1. [전체 설계](design.md): 어떤 대화 경험과 Node·Tool 구조를 만드는가.
2. [코드 따라가기](walkthrough.md): 입력 → 핵심 코드 → 결과를 단계별로 읽는다.
3. [1단계 명세](step-01-state-tool.md): 행사 초안과 조건 변경 Tool의 계약.
4. [Legacy 안내](legacy/README.md): 기존 구현·평가·UI 실행 방법.

작업 순서는 1) 초안 State·조건 변경 Tool → 2) 실제 LLM·LangGraph → 3) UI 연결 → 4) 기록 검색 Tool이다. 1단계의 State·처리기와 27개 테스트를 구현했다. 전체 대화·저장·계획 생성이 완료된 것은 아니다. 관련 #165, #166 / AI-PLAN-01~04.
