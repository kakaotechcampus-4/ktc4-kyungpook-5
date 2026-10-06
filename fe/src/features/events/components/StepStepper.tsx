// 단계 스테퍼: 단계마다 점 · 이름 · 날짜를 가로로 잇는다. 점은 완료(✓) / 진행 중(●) / 예정 3종.
import { cn } from '@/shared/lib/cn'
import type { StepState } from '@/features/events/types'

export interface StepperStep {
  name: string
  // 이미 "3/12"처럼 다듬은 문자열
  date?: string
  state: StepState
}

const DOT: Record<StepState, string> = {
  DONE: 'bg-blue-400 text-[12px] text-white',
  CURRENT: 'border-[2.5px] border-blue-600 bg-card text-[10px] text-blue-600',
  TODO: 'bg-track',
}

const NAME: Record<StepState, string> = {
  DONE: 'font-medium text-ink2',
  CURRENT: 'font-bold text-blue-700',
  TODO: 'font-medium text-mute',
}

const MARK: Record<StepState, string> = { DONE: '✓', CURRENT: '●', TODO: '' }

// 점 모양은 눈으로만 보여서 화면 낭독기에는 글로 알려준다
const STATE_TEXT: Record<StepState, string> = { DONE: '완료', CURRENT: '진행 중', TODO: '예정' }

interface StepStepperProps {
  steps: StepperStep[]
  // 있으면 단계 한 칸(점·이름·날짜)을 눌러 그 단계를 연다(L2 → Step 모달). 없으면 보기만 한다(M1).
  onSelect?: (index: number) => void
}

// 한 칸: 점 줄 · 이름 · 날짜를 세로로 쌓는다
const COLUMN = 'flex min-w-0 flex-1 flex-col items-center gap-[8px]'

export function StepStepper({ steps, onSelect }: StepStepperProps) {
  return (
    <ol className="flex">
      {steps.map((step, i) => {
        // 점 왼쪽 선은 이 단계까지 왔으면, 오른쪽 선은 이 단계를 끝냈으면 파랗다. 양 끝 바깥 선은 숨긴다.
        const leftLine = i === 0 ? 'invisible' : step.state === 'TODO' ? 'bg-soft' : 'bg-blue-400'
        const rightLine =
          i === steps.length - 1 ? 'invisible' : step.state === 'DONE' ? 'bg-blue-400' : 'bg-soft'
        const column = (
          <>
            <div className="flex w-full items-center">
              <span className={cn('h-[2px] flex-1', leftLine)} />
              <span
                className={cn(
                  'flex size-[30px] shrink-0 items-center justify-center rounded-full font-bold',
                  DOT[step.state],
                )}
              >
                {MARK[step.state]}
              </span>
              <span className={cn('h-[2px] flex-1', rightLine)} />
            </div>
            <span className={cn('text-[11.5px] whitespace-nowrap', NAME[step.state])}>
              {step.name}
            </span>
            {step.date && <span className="text-[10px] text-mute">{step.date}</span>}
          </>
        )
        return (
          <li
            key={i}
            aria-current={step.state === 'CURRENT' ? 'step' : undefined}
            className="flex min-w-0 flex-1"
          >
            {onSelect ? (
              // 누를 수 있다는 걸 보이려고 올리면 배경을 깐다. 위아래 여백은 음수 여백으로 상쇄해 자리는 그대로다.
              <button
                type="button"
                onClick={() => onSelect(i)}
                aria-label={`${i + 1}. ${step.name}, ${STATE_TEXT[step.state]}${step.date ? `, ${step.date}` : ''} 자세히 보기`}
                className={cn(
                  COLUMN,
                  '-my-[6px] cursor-pointer rounded-[10px] py-[6px] hover:bg-bg',
                )}
              >
                {column}
              </button>
            ) : (
              <div className={COLUMN}>{column}</div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
