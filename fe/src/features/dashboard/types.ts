// M1 메인 전용 타입

// 토리의 판단과 확인한 근거.
// TODO(연동): GET /clubs/{clubId}/context-decisions의 ContextDecisionOut에 대응한다.
// question → title, reasonSummary → reason, citations[] → evidence[].
// citations가 아직 느슨한 객체 배열이라 모양 고정은 BE에 요청해 둔 상태다.
export interface ToriJudgement {
  title: string
  reason: string
  // 0~5개. label은 "회원 명단 · 32명", source는 "운영진 등록 · 3/6 18:20"처럼 다듬은 문자열
  evidence: Array<{ label: string; source: string }>
}
