// P2 본문. GET /events/{eventId}/plan 의 phases를 그대로 세로 타임라인으로 그린다.
import { useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Input } from '@/shared/ui/Input'
import { cn } from '@/shared/lib/cn'
import { formatMonthDay } from '@/shared/lib/format'
import { ACTOR_DOT_CLASS, ACTOR_LABEL, actionBadge } from '@/features/planning/labels'
import type { PlanPhaseGroup, PlanStep, StepActor, StepPatch } from '@/features/planning/types'

// "3/5" · "3/10–3/12". 시작이 없으면 아직 날짜를 안 잡은 단계다.
function stepDateLabel(step: PlanStep): string {
  if (!step.startedTime) return '미정'
  const start = formatMonthDay(step.startedTime)
  if (!step.deadline) return start
  const end = formatMonthDay(step.deadline)
  return start === end ? start : `${start}–${end}`
}

// 묶음 머리 오른쪽의 "3/5 → 3/7"
function phaseRange(steps: PlanStep[]): string | null {
  const first = steps.find((step) => step.startedTime)?.startedTime
  const lastStep = [...steps].reverse().find((step) => step.deadline ?? step.startedTime)
  const last = lastStep?.deadline ?? lastStep?.startedTime
  return first && last ? `${formatMonthDay(first)} → ${formatMonthDay(last)}` : null
}

function toDateInput(iso: string | null): string {
  return iso ? iso.slice(0, 10) : ''
}

// 날짜만 고치고 시각은 원래 값을 그대로 둔다(마감 23:59 같은 게 날아가지 않게).
function toIso(date: string, previous: string | null): string | null {
  if (!date) return null
  return previous ? `${date}${previous.slice(10)}` : `${date}T00:00:00Z`
}

function StepEditor({
  step,
  onSubmit,
  onCancel,
}: {
  step: PlanStep
  onSubmit: (patch: StepPatch) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(step.name)
  const [startedTime, setStartedTime] = useState(toDateInput(step.startedTime))
  const [deadline, setDeadline] = useState(toDateInput(step.deadline))

  return (
    <div className="flex w-full flex-col gap-[10px] rounded-[10px] border border-[#e3e3e3] bg-white px-[14px] py-[12px]">
      <Input label="단계 이름" value={name} onChange={(event) => setName(event.target.value)} />
      <div className="flex w-full items-end gap-[10px]">
        <Input
          label="시작"
          type="date"
          value={startedTime}
          onChange={(event) => setStartedTime(event.target.value)}
        />
        <Input
          label="마감"
          type="date"
          value={deadline}
          onChange={(event) => setDeadline(event.target.value)}
        />
      </div>
      <div className="flex items-center gap-[8px]">
        <Button
          size="pill"
          disabled={!name.trim()}
          onClick={() =>
            onSubmit({
              name: name.trim(),
              startedTime: toIso(startedTime, step.startedTime),
              deadline: toIso(deadline, step.deadline),
            })
          }
        >
          저장
        </Button>
        <Button variant="secondary" size="pill" onClick={onCancel}>
          취소
        </Button>
      </div>
    </div>
  )
}

interface PlanFlowCardProps {
  phases: PlanPhaseGroup[]
  // "행사 당일 3/21–3/22". 행사 진행 묶음 머리에만 붙는다.
  eventDaysLabel: string | null
  onUpdateStep: (stepId: string, patch: StepPatch) => void
}

export function PlanFlowCard({ phases, eventDaysLabel, onUpdateStep }: PlanFlowCardProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  // 맨 마지막 단계 아래로는 선을 잇지 않는다.
  const lastStepId = phases.flatMap((phase) => phase.steps).at(-1)?.id

  return (
    <Card className="flex min-w-px flex-1 flex-col p-[24px]">
      {phases.map((phase) => (
        <div key={phase.phase} className="flex w-full flex-col">
          <div className="flex h-[34px] w-full items-center gap-[10px]">
            <p className="text-[13.5px] font-medium text-[#1a1a17]">
              {phase.name} · {phase.description}
            </p>
            <div className="h-px flex-1" />
            <p className="text-[11.5px] font-medium whitespace-nowrap text-[#6b6b66]">
              {phase.phase === 'EXECUTION' && eventDaysLabel && `행사 당일 ${eventDaysLabel} · `}
              {phase.steps.length}개 단계
              {phaseRange(phase.steps) && ` · ${phaseRange(phase.steps)}`}
            </p>
          </div>

          {phase.steps.map((step) => (
            <div key={step.id} className="flex w-full items-start gap-[14px]">
              <p className="w-[74px] shrink-0 text-[11.5px] font-medium text-[#6b6b6b]">
                {stepDateLabel(step)}
              </p>

              <div className="flex w-[18px] shrink-0 flex-col items-center self-stretch">
                <span
                  className={cn('size-[14px] shrink-0 rounded-full', ACTOR_DOT_CLASS[step.actor])}
                />
                {step.id !== lastStepId && <span className="w-[2px] flex-1 bg-[#e0e0e0]" />}
              </div>

              <div className="flex min-w-px flex-1 flex-col gap-[7px] pb-[18px]">
                <div className="flex w-full items-center gap-[8px]">
                  <p className="text-[13.5px] font-semibold text-[#262626]">{step.name}</p>
                  {step.actions.map((action) => {
                    const badge = actionBadge(action.type)
                    return badge ? (
                      <Chip key={action.id} variant="subtle">
                        {badge}
                      </Chip>
                    ) : null
                  })}
                  <div className="h-px flex-1" />
                  <button
                    type="button"
                    onClick={() => setEditingId(editingId === step.id ? null : step.id)}
                    className="text-[11.5px] font-medium whitespace-nowrap text-[#737373] hover:text-[#333]"
                  >
                    {editingId === step.id ? '닫기' : '수정'}
                  </button>
                </div>

                {step.actions.map(
                  (action) =>
                    action.subtitle && (
                      <div
                        key={action.id}
                        className="w-full rounded-[10px] bg-[#f8f8f8] px-[14px] py-[11px]"
                      >
                        <p className="text-[12px] text-[#4d4d4d]">{action.subtitle}</p>
                      </div>
                    ),
                )}

                {editingId === step.id && (
                  <StepEditor
                    step={step}
                    onCancel={() => setEditingId(null)}
                    onSubmit={(patch) => {
                      onUpdateStep(step.id, patch)
                      setEditingId(null)
                    }}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      ))}
    </Card>
  )
}

// 머리말 옆 범례. 점 색이 곧 단계의 수행 주체다.
export function PlanActorLegend() {
  return (
    <div className="flex shrink-0 items-center gap-[14px] rounded-[10px] border border-[#e0e0e0] bg-white px-[13px] py-[9px]">
      {(Object.keys(ACTOR_LABEL) as StepActor[]).map((actor) => (
        <div key={actor} className="flex items-center gap-[6px]">
          <span className={cn('size-[9px] shrink-0 rounded-full', ACTOR_DOT_CLASS[actor])} />
          <p className="text-[10.5px] font-medium whitespace-nowrap text-[#595959]">
            {ACTOR_LABEL[actor]}
          </p>
        </div>
      ))}
    </div>
  )
}
