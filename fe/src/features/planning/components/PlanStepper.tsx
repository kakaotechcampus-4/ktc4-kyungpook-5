// 계획 두 단계를 보여주는 머리. 1단계에서 큰 틀을 잡고 2단계에서 흐름을 만든다.
import { cn } from '@/shared/lib/cn'

const STEPS = [
  { no: 1, label: '큰 틀 잡기', desc: '챗봇과 대화' },
  { no: 2, label: '흐름 만들기', desc: '단계 배열 · 일정 · 수금 · 공지' },
]

export function PlanStepper({ current }: { current: 1 | 2 }) {
  return (
    <div className="flex gap-[16px]">
      {STEPS.map((step) => {
        const active = step.no === current
        return (
          <div
            key={step.no}
            aria-current={active}
            className={cn(
              'flex flex-1 items-center gap-[12px] rounded-[14px] border px-[20px] py-[16px]',
              active ? 'border-blue-600 bg-blue-600' : 'border-line bg-card',
            )}
          >
            <span
              className={cn(
                'flex size-[22px] shrink-0 items-center justify-center rounded-full text-[11px] font-bold',
                active ? 'bg-white text-blue-700' : 'bg-track text-mute',
              )}
            >
              {step.no}
            </span>
            <span className="flex flex-col gap-[3px]">
              <span className={cn('text-[13.5px] font-bold', active ? 'text-white' : 'text-ink')}>
                {step.label}
              </span>
              <span className={cn('text-[10.5px]', active ? 'text-blue-100' : 'text-mute')}>
                {step.desc}
              </span>
            </span>
          </div>
        )
      })}
    </div>
  )
}
