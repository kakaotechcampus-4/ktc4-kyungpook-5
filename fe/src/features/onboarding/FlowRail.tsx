import { cn } from '@/shared/lib/cn'

const steps = ['로그인', '팀 선택', '자료 준비', '회의 진행', '할 일 확인']
export function FlowRail({ current, complete = false }: { current: number; complete?: boolean }) {
  return (
    <nav
      aria-label="첫 이용 순서"
      className="mb-6 overflow-x-auto rounded-2xl border border-line bg-card px-3 py-4"
    >
      <ol className="flex min-w-[390px] items-center justify-between gap-2">
        {steps.map((name, index) => (
          <li
            key={name}
            aria-current={current === index + 1 && !complete ? 'step' : undefined}
            className="flex items-center gap-1.5 text-[11px]"
          >
            <span
              className={cn(
                'flex size-5 shrink-0 items-center justify-center rounded-full font-bold',
                index + 1 < current || complete
                  ? 'bg-blue-100 text-blue-700'
                  : index + 1 === current
                    ? 'bg-blue-600 text-white'
                    : 'bg-bg text-mute',
              )}
            >
              {index + 1 < current || complete ? '✓' : index + 1}
            </span>
            <span
              className={
                current === index + 1 && !complete ? 'font-bold text-blue-900' : 'text-mute'
              }
            >
              {name}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  )
}
