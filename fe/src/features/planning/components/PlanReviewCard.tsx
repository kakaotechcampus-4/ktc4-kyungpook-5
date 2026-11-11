// P2 계획 검토 카드 (#177). 상태 판정은 reviewState.ts, 문구는 설계 §4 표.
import type { ReviewCardState } from '@/features/planning/reviewState'
import type { components } from '@/shared/api/schema'
import { Button } from '@/shared/ui/Button'
import { ToriNote } from '@/shared/ui/ToriNote'

type S = components['schemas']

interface PlanReviewCardProps {
  state: ReviewCardState
  review: S['PlanReviewOut'] | null
  onRequest: () => void
  requesting: boolean
}

const ACTION: Partial<Record<ReviewCardState, { title: string; body: string; label: string }>> = {
  request: { title: '고친 계획을 아직 살펴보지 않았어요', body: '', label: '검토 받기' },
  failed: {
    title: '검토하지 못했어요',
    body: '고친 내용은 그대로 저장돼 있어요',
    label: '다시 시도',
  },
  stale: {
    title: '검토한 뒤로 계획이 더 바뀌었어요',
    body: '지난 검토 결과는 지금 계획과 맞지 않아 지웠어요',
    label: '다시 검토',
  },
}

export function PlanReviewCard({ state, review, onRequest, requesting }: PlanReviewCardProps) {
  if (state === 'hidden') return null
  if (state === 'reviewing') return <ToriNote title="고친 계획을 살펴보고 있어요" />
  if (state === 'clear')
    return <ToriNote title="이번 검토에서는 추가로 짚을 주의점을 찾지 못했어요" />
  if (state === 'issues') {
    return (
      <ToriNote title="이런 점을 확인해 보세요" tone="cream">
        <ul className="flex flex-col gap-[10px]">
          {(review?.items ?? []).map((item, index) => (
            <li key={index} className="flex flex-col gap-[2px]">
              <span className="font-bold">{item.stepNames.join(' · ')}</span>
              <span>{item.message}</span>
              {item.suggestion && <span>{item.suggestion}</span>}
            </li>
          ))}
        </ul>
      </ToriNote>
    )
  }
  const action = ACTION[state]
  if (!action) return null
  return (
    <ToriNote title={action.title} tone={state === 'failed' ? 'cream' : 'blue'}>
      <span className="flex flex-col gap-[12px]">
        {action.body && <span>{action.body}</span>}
        <Button
          variant="secondary"
          size="sm"
          className="w-full"
          disabled={requesting}
          onClick={onRequest}
        >
          {action.label}
        </Button>
      </span>
    </ToriNote>
  )
}
