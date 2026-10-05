// L2 행사 상세: 한 행사의 단계 진행과 확인 요청 · 처리된 승인을 본다.
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ConfirmationList } from '@/features/events/components/ConfirmationList'
import { CurrentStepCard } from '@/features/events/components/CurrentStepCard'
import { EventHeaderCard } from '@/features/events/components/EventHeaderCard'
import { ResolvedActionList } from '@/features/events/components/ResolvedActionList'
import {
  useConfirmations,
  useEventDetail,
  useEventSteps,
  useResolvedActions,
} from '@/features/events/hooks'
import type { EventAction } from '@/features/events/types'
import { toast } from '@/shared/lib/toast'
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
  // 행사가 없으면(초기 화면) 나머지는 부르지 않는다
  const shownId = event ? eventId : undefined
  const steps = useEventSteps(shownId).data ?? []
  const currentIndex = steps.findIndex((s) => s.state === 'CURRENT')
  const resolved = useResolvedActions(shownId).data

  // 처리한 확인 요청. 서버 연동 전이라 화면에서만 빼 둔다.
  const [answeredIds, setAnsweredIds] = useState<string[]>([])
  const confirmations = (useConfirmations(shownId).data ?? []).filter(
    (a) => !answeredIds.includes(a.id),
  )

  // TODO(연동): POST /actions/{id}/resolve 에 { choice } 로 보낸다
  const resolveConfirmation = (action: EventAction, choice: string) => {
    setAnsweredIds((ids) => [...ids, action.id])
    toast.show({
      kind: 'done',
      title: choice === 'MANUAL' ? '직접 처리로 넘겼어요' : '처리했어요',
      desc: action.title,
    })
  }

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
        <>
          <EventHeaderCard event={event} steps={steps} />
          <div className="flex items-start gap-[20px]">
            <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
              <ConfirmationList actions={confirmations} onResolve={resolveConfirmation} />
              <ResolvedActionList
                actions={resolved?.items ?? []}
                totalCount={resolved?.totalCount ?? 0}
              />
            </div>
            {/* 진행 중인 단계가 없으면(계획 중 · 끝난 행사) 오른쪽 칸 없이 왼쪽이 넓어진다 */}
            {currentIndex >= 0 && (
              <CurrentStepCard
                className="w-[400px] shrink-0"
                step={steps[currentIndex]}
                position={currentIndex + 1}
              />
            )}
          </div>
        </>
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
