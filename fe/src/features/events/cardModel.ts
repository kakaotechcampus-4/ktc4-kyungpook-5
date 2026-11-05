// 행사 카드(L1)의 단계 칸 · 상태 칸 문구와 진행 바 표시 여부.
// 계획 중에는 단계 진행이 시작되지 않았으므로 서버의 단계 상태를 보지 않고 초안 단계 수만 보여 준다(#337).
import type { EventStatus, EventSummary } from '@/features/events/types'

export function showsProgress(status: EventStatus): boolean {
  return status !== 'PLANNING'
}

export function cardStepText(event: EventSummary): string {
  const total = event.stepProgress.length
  if (event.status === 'PLANNING') return total > 0 ? `${total}단계` : '—'
  // 진행 중인 단계까지 센다(완료 + 진행 중)
  const reached = event.stepProgress.filter((s) => s.state !== 'TODO').length
  return `${reached} / ${total}`
}

// 진행 중이면 승인 대기 건수, 계획 중이면 초안 단계 수, 끝났으면 정산 완료
export function cardStatusText(event: EventSummary): string {
  if (event.status === 'COMPLETE') return '정산 완료'
  if (event.status === 'CANCELLED') return '취소 정리 완료'
  if (event.status === 'CANCELLING') return '취소 정리 중'
  if (event.status === 'PLANNING') {
    const total = event.stepProgress.length
    return total > 0 ? `계획 중 · 초안 ${total}단계` : '계획 중 · 초안 없음'
  }
  if (event.pendingApprovalCount > 0) return `승인 대기 ${event.pendingApprovalCount}건`
  return event.currentStepName ?? '진행 중'
}
