// M1 메인 전용 타입

// 토리의 판단과 확인한 근거.
// TODO: API 명세에 아직 없다. 엔드포인트가 정해지면 모양을 맞춘다.
export interface ToriJudgement {
  title: string
  reason: string
  // 0~5개. label은 "회원 명단 · 32명", source는 "운영진 등록 · 3/6 18:20"처럼 다듬은 문자열
  evidence: Array<{ label: string; source: string }>
}
