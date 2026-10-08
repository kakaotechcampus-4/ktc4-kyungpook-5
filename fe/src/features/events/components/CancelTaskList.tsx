// 취소 정리 할 일. 네 가지로 고정이고 앱이 대신 취소해주지 않는다 —
// 운영진이 직접 처리한 뒤 완료로 표시한다.
import type { CancelTask } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

interface CancelTaskListProps {
  tasks: CancelTask[]
  onShowMessage: (task: CancelTask) => void
  onComplete: (task: CancelTask) => void
}

export function CancelTaskList({ tasks, onShowMessage, onComplete }: CancelTaskListProps) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-center gap-[9px] px-[26px] pt-[22px] pb-[16px]">
        <h2 className="text-h2 text-ink">취소 정리 할 일</h2>
        <Chip tone="approved">{tasks.length}개</Chip>
        <span className="text-[11.5px] text-mute">직접 진행하고 완료로 표시해요</span>
      </div>

      {tasks.map((task) => (
        <div
          key={task.id}
          className={cn(
            'flex items-center gap-[14px] border-t border-line px-[26px] py-[15px]',
            task.state === 'CURRENT' && 'bg-blue-50',
          )}
        >
          <span className="flex min-w-0 flex-1 flex-col gap-[4px]">
            <span
              className={cn(
                'truncate text-[13.5px] font-bold',
                task.state === 'TODO' ? 'text-ink2' : 'text-ink',
              )}
            >
              {task.name}
            </span>
            <span className="text-[11.5px] text-mute">{task.desc}</span>
          </span>

          {task.state === 'DONE' && (
            <Chip tone="done" size="sm">
              완료
            </Chip>
          )}
          {task.state === 'TODO' && <Chip size="sm">대기</Chip>}
          {task.state === 'CURRENT' && (
            <span className="flex shrink-0 gap-[8px]">
              {task.message && (
                <Button variant="secondary" onClick={() => onShowMessage(task)}>
                  연락 문구 보기
                </Button>
              )}
              {/* TODO(연동): 취소 단계 완료 API는 아직 정의 전이다(#73). */}
              <Button onClick={() => onComplete(task)}>완료로 표시</Button>
            </span>
          )}
        </div>
      ))}
    </Card>
  )
}
