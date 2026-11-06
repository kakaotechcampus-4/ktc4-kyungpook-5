// P2-b 단계 구성 변경 주소. 계획 검토에서는 같은 자리 편집 모드로 바로 열리고,
// 이 주소는 데모와 다른 화면에서 들어오는 길로 남겨 둔다. 그리는 것은 같은 StepComposer다.
import { useNavigate, useSearchParams } from 'react-router-dom'
import { StepComposer } from '@/features/planning/components/StepComposer'

export default function PlanStepsPage() {
  const navigate = useNavigate()
  // 다른 화면과 같은 방식. ?demo면 10개가 들어간 상태를 보인다.
  const params = useSearchParams()[0]
  const demo = params.has('demo')
  const eventId = params.get('eventId')
  const returnToEvent = params.get('from') === 'event' && eventId
  const goBack = () =>
    returnToEvent
      ? navigate(`/events/${encodeURIComponent(returnToEvent)}`)
      : eventId
        ? navigate(`/planning?${new URLSearchParams({ eventId, stage: 'review' })}`)
        : navigate(-1)

  return (
    <div className="flex flex-col gap-[20px]">
      <h1 className="text-h1">단계 구성 변경</h1>
      <StepComposer eventId={eventId} demo={demo} onDone={goBack} />
    </div>
  )
}
