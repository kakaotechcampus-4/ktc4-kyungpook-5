// M1 메인(AI 비서): 진행 중인 행사에서 결정이 필요한 일만 모아 보여준다.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApprovalList } from '@/features/dashboard/components/ApprovalList'
import { EventSummaryCard } from '@/features/dashboard/components/EventSummaryCard'
import { ToriJudgementCard } from '@/features/dashboard/components/ToriJudgementCard'
import type { ToriJudgement } from '@/features/dashboard/types'
import type { EventAction, EventStep, EventSummary } from '@/features/events/types'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'

export default function MainPage() {
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState<string>()

  // 승인·거절한 Action. 서버 연동 전이라 화면에서만 빼 둔다.
  const [resolvedIds, setResolvedIds] = useState<string[]>([])

  // TODO: API 연동 전까지는 비어 있다.
  // GET /events?status=ON_GOING · GET /events/{id}/steps
  // GET /events/{id}/actions?status=PENDING&excludeType=CONFIRMATION · 토리의 판단(명세 없음)
  const events: EventSummary[] = []
  const stepsByEvent: Record<string, EventStep[]> = {}
  const actionsByEvent: Record<string, EventAction[]> = {}
  const judgementByEvent: Record<string, ToriJudgement> = {}

  // 고른 행사가 없으면 첫 번째 행사를 보여준다
  const selected = events.find((e) => e.id === selectedId) ?? events[0]
  const actions = selected
    ? (actionsByEvent[selected.id] ?? []).filter((a) => !resolvedIds.includes(a.id))
    : []
  const judgement = selected && judgementByEvent[selected.id]

  // TODO: POST /actions/{id}/approve · /deny 가 생기면 서버에 보낸다.
  const resolve = (action: EventAction, approved: boolean) => {
    setResolvedIds((ids) => [...ids, action.id])
    toast.show({
      kind: 'done',
      title: approved ? '승인했어요' : '승인하지 않았어요',
      desc: action.title,
    })
  }

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex items-center justify-between">
        <div className="flex flex-col gap-[4px]">
          <h1 className="text-h1">AI 비서</h1>
          <p className="text-mute">결정이 필요한 일만 올려요. 승인한 일은 직접 진행해 주세요.</p>
        </div>
        {selected && (
          <Button variant="secondary" onClick={() => navigate(`/events/${selected.id}`)}>
            행사 상세 보기
          </Button>
        )}
      </header>

      {selected ? (
        <>
          <EventSummaryCard
            events={events}
            selected={selected}
            onSelect={setSelectedId}
            steps={stepsByEvent[selected.id] ?? []}
          />
          <div className="flex items-start gap-[20px]">
            <ApprovalList
              className="min-w-0 flex-1"
              actions={actions}
              onApprove={(a) => resolve(a, true)}
              onDeny={(a) => resolve(a, false)}
            />
            {judgement && (
              <ToriJudgementCard className="w-[404px] shrink-0" judgement={judgement} />
            )}
          </div>
        </>
      ) : (
        <EmptyState
          title="아직 진행 중인 행사가 없어요"
          desc="행사 계획을 시작하면 제가 단계를 만들고, 승인이 필요한 일만 모아서 여기에 올려드릴게요."
          action={
            <Button size="lg" className="text-[13px]" onClick={() => navigate('/planning')}>
              행사 계획 시작하기
            </Button>
          }
        />
      )}
    </div>
  )
}
