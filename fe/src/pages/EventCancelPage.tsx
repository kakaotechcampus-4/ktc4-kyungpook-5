// L2-d 행사 취소 정리. 취소를 누른 뒤 뒷정리를 차례로 안내한다.
// 앱이 대신 취소해주지 않는다 — 운영진이 직접 하고 완료로 표시한다.
import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { CancelTaskList } from '@/features/events/components/CancelTaskList'
import { ResolvedActionList } from '@/features/events/components/ResolvedActionList'
import { StepStepper } from '@/features/events/components/StepStepper'
import { useEventDetail, useResolvedActions } from '@/features/events/hooks'
import { DEMO_CANCEL_TASKS, EMPTY_CANCEL_TASKS } from '@/features/events/mock'
import type { CancelTask } from '@/features/events/types'
import { copyText } from '@/shared/lib/clipboard'
import { formatDateRange } from '@/shared/lib/format'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ToriNote } from '@/shared/ui/ToriNote'

export default function EventCancelPage() {
  const { eventId } = useParams()
  const { search } = useLocation()
  const demo = new URLSearchParams(search).has('demo')

  const event = useEventDetail(eventId).data
  const resolved = useResolvedActions(eventId).data

  // TODO(연동): 취소 단계·Action은 아직 정의 전이다(#73).
  const [tasks, setTasks] = useState<CancelTask[]>(demo ? DEMO_CANCEL_TASKS : EMPTY_CANCEL_TASKS)
  const current = tasks.find((t) => t.state === 'CURRENT')
  const doneCount = tasks.filter((t) => t.state === 'DONE').length

  // 하나를 끝내면 다음 것이 진행 중이 된다.
  const complete = (task: CancelTask) => {
    setTasks((list) => {
      const index = list.findIndex((t) => t.id === task.id)
      return list.map((t, i) =>
        i === index ? { ...t, state: 'DONE' } : i === index + 1 ? { ...t, state: 'CURRENT' } : t,
      )
    })
    toast.show({ kind: 'done', title: '완료로 표시했어요', desc: task.name })
  }

  const showMessage = (task: CancelTask) => {
    if (!task.message) return
    copyText(task.message)
    toast.show({ kind: 'done', title: '연락 문구를 복사했어요', desc: task.name })
  }

  const meta = [
    { label: '행사일', value: event ? formatDateRange(event.startDate, event.endDate) : '—' },
    { label: '장소', value: event?.location ?? '—' },
    { label: '참가', value: event?.headcount ? `${event.headcount}명` : '—' },
    { label: '정리 단계', value: current?.name ?? '정리 완료', highlight: true },
    { label: '담당', value: '박수겸 · 총무' },
  ]

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
            <Chip tone="failed">취소 정리 중</Chip>
          </span>
          {/* TODO(연동): 정리 단계를 바꾸는 화면은 취소 Action이 정해진 뒤에 만든다(#73). */}
          <Button variant="secondary">정리 단계 수정</Button>
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
          <CancelTaskList tasks={tasks} onShowMessage={showMessage} onComplete={complete} />
          <ResolvedActionList
            actions={resolved?.items ?? []}
            totalCount={resolved?.totalCount ?? 0}
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

            {current.message && (
              <Button variant="soft" className="w-full" onClick={() => showMessage(current)}>
                연락 문구 보기
              </Button>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
