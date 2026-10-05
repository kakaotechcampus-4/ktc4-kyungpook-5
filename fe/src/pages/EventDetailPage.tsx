// L2 행사 상세: 한 행사의 단계 진행과 확인 요청 · 처리된 승인을 본다.
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { EventHeaderCard } from '@/features/events/components/EventHeaderCard'
import { useEventDetail, useEventSteps } from '@/features/events/hooks'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'
import { ServerErrorScreen } from '@/shared/ui/StateScreen'

export default function EventDetailPage() {
  const { eventId } = useParams()
  // ?demo 같은 주소 뒤쪽을 행사 목록으로 돌아갈 때도 이어 붙인다
  const { search } = useLocation()
  const navigate = useNavigate()
  const toList = `/events${search}`

  const detailQuery = useEventDetail(eventId)
  const event = detailQuery.data
  const steps = useEventSteps(event ? eventId : undefined).data ?? []

  if (detailQuery.isPending) return null
  if (detailQuery.isError) {
    return <ServerErrorScreen onRetry={() => detailQuery.refetch()} onHome={() => navigate('/')} />
  }

  return (
    <div className="flex flex-col gap-[20px]">
      <nav aria-label="이동 경로" className="flex items-center gap-[8px] text-[12px]">
        <Link
          to={toList}
          aria-label="행사 목록으로"
          className="rounded-[8px] border border-soft bg-card px-[9px] py-[5px] font-medium text-ink2 hover:bg-bg"
        >
          ‹
        </Link>
        <span className="text-mute">행사 목록</span>
        {event && (
          <>
            <span className="text-mute">/</span>
            <span className="font-bold">{event.title}</span>
          </>
        )}
      </nav>

      {event ? (
        <EventHeaderCard event={event} steps={steps} />
      ) : (
        <EmptyState
          title="아직 등록된 행사가 없어요"
          desc="행사를 만들면 여기서 단계 진행과 승인 기록을 볼 수 있어요."
          action={
            <div className="flex gap-[9px]">
              <Button size="lg" className="text-[13px]" onClick={() => navigate('/planning')}>
                행사 만들기
              </Button>
              <Button variant="secondary" size="lg" onClick={() => navigate(toList)}>
                행사 목록으로
              </Button>
            </div>
          }
        />
      )}
    </div>
  )
}
