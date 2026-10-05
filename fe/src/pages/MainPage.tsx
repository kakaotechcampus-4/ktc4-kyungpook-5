// M1 메인(AI 비서): 진행 중인 행사에서 결정이 필요한 일만 모아 보여준다.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApprovalList } from '@/features/dashboard/components/ApprovalList'
import { EventSummaryCard } from '@/features/dashboard/components/EventSummaryCard'
import { ToriJudgementCard } from '@/features/dashboard/components/ToriJudgementCard'
import { useToriJudgement } from '@/features/dashboard/hooks'
import { useEventSteps, useEvents, usePendingApprovals } from '@/features/events/hooks'
import type { EventAction } from '@/features/events/types'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'
import { ServerErrorScreen } from '@/shared/ui/StateScreen'

export default function MainPage() {
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState<string>()

  // 승인·거절한 Action. 서버 연동 전이라 화면에서만 빼 둔다.
  const [resolvedIds, setResolvedIds] = useState<string[]>([])

  const eventsQuery = useEvents('ON_GOING')
  const events = eventsQuery.data ?? []

  // 고른 행사가 없으면 첫 번째 행사를 보여준다
  const selected = events.find((e) => e.id === selectedId) ?? events[0]
  const steps = useEventSteps(selected?.id).data ?? []
  const actions = (usePendingApprovals(selected?.id).data ?? []).filter(
    (a) => !resolvedIds.includes(a.id),
  )
  const judgement = useToriJudgement(selected?.id)

  // TODO: POST /actions/{id}/approve · /deny 가 생기면 서버에 보낸다.
  const resolve = (action: EventAction, approved: boolean) => {
    setResolvedIds((ids) => [...ids, action.id])
    toast.show({
      kind: 'done',
      title: approved ? '승인했어요' : '승인하지 않았어요',
      desc: action.title,
    })
  }

  // 목록을 받기 전에 빈 상태를 그리면 "진행 중인 행사가 없어요"가 잠깐 깜빡인다
  if (eventsQuery.isPending) return null
  if (eventsQuery.isError) {
    return <ServerErrorScreen onRetry={() => eventsQuery.refetch()} onHome={() => navigate('/')} />
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
            steps={steps}
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
