// P2 왼쪽: 포함된 단계를 묶음별로 늘어놓는다. 날짜와 점 색, 연결선으로 순서를 보인다.
// 묶음은 셋으로 고정이지만 포함된 단계가 없는 묶음은 그리지 않는다.
import type { PlanStep, StepActor, StepPhase } from '@/features/planning/types'
import { cn } from '@/shared/lib/cn'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

const PHASES: StepPhase[] = ['사전 준비', '모집 · 확정', '행사 진행 · 마무리']

const PHASE_DESC: Record<StepPhase, string> = {
  '사전 준비': '인원과 예산의 윤곽을 잡습니다',
  '모집 · 확정': '자리를 잡고 참가비를 걷습니다',
  '행사 진행 · 마무리': '돈을 정산하고 기록을 남깁니다',
}

// 담당은 점 색으로만 구분한다. 글자로 또 적으면 줄이 길어진다.
const ACTOR_DOT: Record<StepActor, string> = {
  'AI 실행': 'bg-blue-600',
  '승인 필요': 'bg-pending',
  '직접 수행': 'border border-soft bg-card',
}

function Legend() {
  return (
    <div className="flex items-center gap-[14px]">
      {(Object.keys(ACTOR_DOT) as StepActor[]).map((actor) => (
        <span key={actor} className="flex items-center gap-[6px]">
          <span className={cn('size-[8px] shrink-0 rounded-full', ACTOR_DOT[actor])} />
          <span className="text-[11px] text-mute">{actor}</span>
        </span>
      ))}
    </div>
  )
}

interface StepFlowProps {
  steps: PlanStep[]
  onEditStep: (step: PlanStep) => void
}

export function StepFlow({ steps, onEditStep }: StepFlowProps) {
  return (
    <Card className="flex min-w-0 flex-1 flex-col gap-[20px] px-[24px] pt-[22px] pb-[26px]">
      <div className="flex items-center gap-[14px]">
        <h2 className="text-h2 text-ink">단계 흐름</h2>
        <Legend />
      </div>

      {PHASES.map((phase) => {
        const rows = steps.filter((s) => s.phase === phase)
        if (rows.length === 0) return null
        // 날짜가 있는 단계만으로 범위를 잡는다. 「미정 → 미정」·「3/5 → 3/5」는 읽히지 않는다.
        const dates = rows.map((s) => s.date).filter((date) => date !== '미정')
        const span = !dates.length
          ? '일정 미정'
          : dates[0] === dates[dates.length - 1]
            ? dates[0]
            : `${dates[0]} → ${dates[dates.length - 1]}`
        return (
          <section key={phase} className="flex flex-col gap-[10px]">
            <div className="flex items-end justify-between gap-[12px]">
              <span className="flex flex-col gap-[3px]">
                <span className="text-h3 text-ink">{phase}</span>
                <span className="text-[11px] text-mute">{PHASE_DESC[phase]}</span>
              </span>
              <span className="text-[11px] text-mute">
                {rows.length}개 단계 · {span}
              </span>
            </div>

            {rows.map((step, i) => (
              <div key={step.id} className="flex gap-[12px]">
                {/* 날짜 + 점 + 연결선. 마지막 줄은 선을 그리지 않는다. */}
                <div className="flex w-[42px] shrink-0 flex-col items-center pt-[4px]">
                  <span className="text-[10.5px] text-mute">{step.date}</span>
                  <span
                    className={cn(
                      'mt-[5px] size-[9px] shrink-0 rounded-full',
                      ACTOR_DOT[step.actor],
                    )}
                  />
                  {i < rows.length - 1 && <span className="mt-[4px] w-px flex-1 bg-line" />}
                </div>

                <div className="mb-[2px] flex min-w-0 flex-1 flex-col gap-[6px] rounded-[12px] bg-bg px-[16px] pt-[13px] pb-[14px]">
                  <div className="flex items-center justify-between gap-[10px]">
                    <span className="flex min-w-0 items-center gap-[8px]">
                      <span className="truncate text-[13.5px] font-bold text-ink">{step.name}</span>
                      {step.actionLabel && <Chip size="sm">{step.actionLabel}</Chip>}
                    </span>
                    {/* 끝난 단계도 열어 볼 수는 있다. 입력은 모달이 잠근다. */}
                    <button
                      type="button"
                      // 줄마다 「수정」이라 화면 낭독기에서 구분되게 단계 이름을 붙인다.
                      aria-label={`${step.name} ${step.editable === false ? '보기' : '수정'}`}
                      onClick={() => onEditStep(step)}
                      className={cn(
                        'shrink-0 text-[11.5px] font-bold hover:underline',
                        step.editable === false ? 'text-mute' : 'text-blue-700',
                      )}
                    >
                      {step.editable === false ? '보기' : '수정'}
                    </button>
                  </div>
                  {step.desc && (
                    <p className="text-[11.5px] leading-[17px] text-ink2">{step.desc}</p>
                  )}
                </div>
              </div>
            ))}
          </section>
        )
      })}
    </Card>
  )
}
