// M1 메인(AI 비서): 진행 중인 행사에서 결정이 필요한 일만 모아 보여준다.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EventSummaryCard } from '@/features/dashboard/components/EventSummaryCard'
import type { EventStep, EventSummary } from '@/features/events/types'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'

export default function MainPage() {
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState<string>()

  // TODO: API 연동 전까지는 비어 있다. GET /events?status=ON_GOING · GET /events/{id}/steps
  const events: EventSummary[] = []
  const stepsByEvent: Record<string, EventStep[]> = {}

  // 고른 행사가 없으면 첫 번째 행사를 보여준다
  const selected = events.find((e) => e.id === selectedId) ?? events[0]

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
        <EventSummaryCard
          events={events}
          selected={selected}
          onSelect={setSelectedId}
          steps={stepsByEvent[selected.id] ?? []}
        />
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
