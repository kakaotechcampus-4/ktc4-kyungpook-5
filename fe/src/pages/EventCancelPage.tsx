// L2-d 행사 취소 정리. 취소를 누른 뒤 뒷정리를 차례로 안내한다.
// 앱이 대신 취소해주지 않는다 — 운영진이 직접 하고 완료로 표시한다.
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { CancelTaskList } from '@/features/events/components/CancelTaskList'
import { ResolvedActionList } from '@/features/events/components/ResolvedActionList'
import { StepStepper } from '@/features/events/components/StepStepper'
import { useEventDetail, useResolvedActions, useCancelTasks, useCompleteCancelTask } from '@/features/events/hooks'
import { DEMO_CANCEL_TASKS } from '@/features/events/mock'
import type { CancelTask } from '@/features/events/types'
import { copyText } from '@/shared/lib/clipboard'
import { formatDateRange } from '@/shared/lib/format'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ServerErrorScreen } from '@/shared/ui/StateScreen'
import { ToriNote } from '@/shared/ui/ToriNote'

export default function EventCancelPage() {
  const { eventId } = useParams()
  const { search } = useLocation()
  const navigate = useNavigate()
  const demo = new URLSearchParams(search).has('demo')

  const detailQuery = useEventDetail(eventId)
  const event = detailQuery.data
  // 「전체 보기」를 누르면 처리 기록을 전부 받아 그 자리에서 펼친다
  const [allResolved, setAllResolved] = useState(false)
  const resolvedQuery = useResolvedActions(eventId, allResolved)
  const resolved = resolvedQuery.data
  const cancelQuery = useCancelTasks(eventId)
  const completeMutation = useCompleteCancelTask()

  const [demoTasks, setDemoTasks] = useState<CancelTask[]>(DEMO_CANCEL_TASKS)
  const tasks: CancelTask[] = demo
    ? demoTasks
    : (cancelQuery.data ?? []).map((task) => ({ id: task.id, name: task.name, desc: task.description, state: task.state, message: task.message ?? undefined }))
  const current = tasks.find((t) => t.state === 'CURRENT')
  const doneCount = tasks.filter((t) => t.state === 'DONE').length

  // 하나를 끝내면 다음 것이 진행 중이 된다.
  const complete = (task: CancelTask) => {
    setDemoTasks((list) => {
      const index = list.findIndex((t) => t.id === task.id)
      return list.map((t, i) =>
        i === index ? { ...t, state: 'DONE' } : i === index + 1 ? { ...t, state: 'CURRENT' } : t,
      )
    })
    toast.show({ kind: 'done', title: '완료로 표시했어요', desc: task.name })
  }

  const completeServer = (task: CancelTask) => {
    if (!eventId) return
    completeMutation.mutate(
      { eventId, taskId: task.id },
      {
        onSuccess: () => toast.show({ kind: 'done', title: '완료로 표시했어요', desc: task.name }),
        onError: (error) => toast.show({ kind: 'error', title: '처리하지 못했어요', desc: error instanceof Error ? error.message : '잠시 후 다시 시도해 주세요.' }),
      },
    )
  }

  const copyMessage = async (task: CancelTask) => {
    if (!task.message) return
    const ok = await copyText(task.message)
    toast.show(
      ok
        ? { kind: 'done', title: '연락 문구를 복사했어요', desc: task.name }
        : {
            kind: 'error',
            title: '복사하지 못했어요',
            desc: '오른쪽 연락 문구를 직접 골라서 복사해 주세요.',
          },
    )
  }

  const meta = [
    { label: '행사일', value: event ? formatDateRange(event.startDate, event.endDate) : '—' },
    { label: '장소', value: event?.location ?? '—' },
    { label: '참가', value: event?.headcount ? `${event.headcount}명` : '—' },
    { label: '정리 단계', value: current?.name ?? '정리 완료', highlight: true },
  ]

  // 행사 상세와 같은 방식. 받기 전에는 그리지 않고, 실패하면 자리값 대신 오류 화면을 보인다.
  if (detailQuery.isPending) return null
  if (detailQuery.isError) {
    return <ServerErrorScreen onRetry={() => detailQuery.refetch()} onHome={() => navigate('/')} />
  }
  if (!demo && cancelQuery.isPending) return null
  if (!demo && cancelQuery.isError) {
    return <ServerErrorScreen onRetry={() => cancelQuery.refetch()} onHome={() => navigate('/')} />
  }

  return (
    <div className="flex flex-col gap-[20px]">
      <nav className="flex items-center gap-[8px] text-[11.5px] text-mute">
        <Link to={`/events${search}`} className="hover:text-ink2">
          ‹ 행사 목록
        </Link>
        <span>/</span>
        <span className="font-bold text-ink2">{event?.title ?? '행사 이름'}</span>
      </nav>

      <Card className="flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]">
        <div className="flex items-center justify-between gap-[12px]">
          <span className="flex items-center gap-[10px]">
            <h1 className="text-h1">{event?.title ?? '행사 이름'}</h1>
            <Chip tone={event?.status === 'CANCELLED' ? 'done' : 'failed'}>{event?.status === 'CANCELLED' ? '취소 완료' : '취소 정리 중'}</Chip>
          </span>
        </div>

        <div className="flex flex-wrap gap-x-[36px] gap-y-[12px]">
          {meta.map((item) => (
            <span key={item.label} className="flex flex-col gap-[4px]">
              <span className="text-[10.5px] font-medium text-mute">{item.label}</span>
              <span
                className={
                  item.highlight
                    ? 'text-[13.5px] font-bold text-blue-700'
                    : 'text-[13.5px] font-bold text-ink'
                }
              >
                {item.value}
              </span>
            </span>
          ))}
        </div>

        <div className="flex items-center gap-[20px] border-t border-line pt-[20px]">
          <div className="min-w-0 flex-1">
            <StepStepper
              steps={tasks.map((t) => ({
                name: t.name,
                state: t.state,
                deadline: t.date ?? null,
              }))}
            />
          </div>
          <span className="flex shrink-0 flex-col items-center gap-[3px] rounded-[14px] bg-blue-50 px-[22px] py-[14px]">
            <span className="text-[20px] font-bold text-blue-700">
              {doneCount} / {tasks.length}
            </span>
            <span className="text-[10.5px] text-blue-700">정리 진행</span>
          </span>
        </div>
      </Card>

      <div className="flex items-start gap-[20px]">
        <div className="flex min-w-0 flex-1 flex-col gap-[20px]">
          <CancelTaskList tasks={tasks} onCopyMessage={copyMessage} onComplete={demo ? complete : completeServer} pending={!demo && completeMutation.isPending} />
          <ResolvedActionList
            actions={resolved?.items ?? []}
            totalCount={resolved?.totalCount ?? 0}
            expanded={allResolved}
            onExpand={() => setAllResolved(true)}
            loadingMore={allResolved && resolvedQuery.isFetching}
          />
        </div>

        {current && (
          <Card className="flex w-[360px] shrink-0 flex-col gap-[16px] px-[22px] pt-[20px] pb-[22px]">
            <div className="flex items-center gap-[9px]">
              <h2 className="text-h3 text-ink">
                {tasks.indexOf(current) + 1}. {current.name}
              </h2>
              <Chip tone="approved" size="sm">
                진행 중
              </Chip>
            </div>
            <span className="text-[11px] text-mute">직접 진행</span>

            {current.note && <ToriNote title="이 단계에서 할 일">{current.note}</ToriNote>}

            {current.todos && (
              <div className="flex flex-col gap-[7px]">
                <span className="text-[12px] font-bold text-ink">남은 일</span>
                {current.todos.map((todo) => (
                  <span key={todo} className="text-[11.5px] leading-[17px] text-ink2">
                    · {todo}
                  </span>
                ))}
              </div>
            )}

            {/* 복사가 막혀도 직접 골라 복사할 수 있게 문구를 그대로 보여준다 */}
            {current.message && (
              <div className="flex flex-col gap-[7px]">
                <span className="text-[12px] font-bold text-ink">연락 문구</span>
                <p className="rounded-[11px] bg-bg px-[14px] py-[12px] text-[12px] leading-[18px] whitespace-pre-line text-ink2">
                  {current.message}
                </p>
                <Button variant="soft" className="w-full" onClick={() => copyMessage(current)}>
                  연락 문구 복사
                </Button>
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
