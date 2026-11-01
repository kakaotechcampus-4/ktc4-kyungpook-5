// 계획 검토 카드 상태 판정. 순수 함수라 import 없이 node --test로 바로 돌린다.
// 우선순위: 요청 진행 중 > 서버 REVIEWING > 버전 불일치 > 서버 결과. (설계 §4)
export type ReviewCardState =
  'hidden' | 'request' | 'reviewing' | 'issues' | 'clear' | 'failed' | 'stale'

export type ReviewSnapshot = {
  status: 'NOT_REQUESTED' | 'REVIEWING' | 'DONE' | 'FAILED'
  generatedRevision: number
  reviewedRevision: number | null
  // 'issues' | 'no_issues'. 생성된 스키마가 string으로 내려준다.
  outcome: string | null
}

export function reviewCardState(input: {
  planRevision: number
  review: ReviewSnapshot | null
  requesting: boolean
}): ReviewCardState {
  const { planRevision, review, requesting } = input
  if (requesting) return 'reviewing'
  if (!review) return 'hidden'
  if (review.status === 'REVIEWING') return 'reviewing'
  const edited = review.generatedRevision < planRevision
  if (review.status === 'NOT_REQUESTED' || review.reviewedRevision === null) {
    return edited ? 'request' : 'hidden'
  }
  if (review.reviewedRevision !== planRevision) return 'stale'
  if (review.status === 'FAILED') return 'failed'
  return review.outcome === 'issues' ? 'issues' : 'clear'
}

// 생성 시 경고는 계획을 고친 뒤에는 낡은 정보라 숨긴다.
export function showGenerationWarnings(planRevision: number, review: ReviewSnapshot | null) {
  return !review || review.generatedRevision >= planRevision
}
