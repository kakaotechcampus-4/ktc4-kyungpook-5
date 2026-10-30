// 단계 세부 수정(#106). 일정은 모든 단계에 공통이고, 나머지 밭은 그 단계에 붙은
// Action 유형이 정한다. 저장은 아직 이 브라우저에만 남는다(#213).
import { useState } from 'react'
import type { CatalogueStep } from '@/features/planning/catalogue'
import type { LocalSchedule } from '@/features/planning/localPlan'
import { DERIVES_TO_EVENT, fieldsForStep, type FieldSpec } from '@/features/planning/stepDetail'
import { Button } from '@/shared/ui/Button'
import { Field } from '@/shared/ui/AuthShell'
import { Input } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'

// <input type="date">는 yyyy-MM-dd만 받는다. 돌려줄 때는 그날 0시(한국)를 붙여
// 서버가 줄 ISO 와 같은 모양으로 맞춘다.
const toDateInput = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : '')
const fromDateInput = (value: string) => (value ? `${value}T00:00:00+09:00` : null)

interface StepDetailModalProps {
  step: CatalogueStep | null
  value: LocalSchedule
  onClose: () => void
  onSave: (next: LocalSchedule) => void
}

export function StepDetailModal({ step, value, onClose, onSave }: StepDetailModalProps) {
  if (!step) return null
  return (
    <StepDetailForm key={step.code} step={step} value={value} onClose={onClose} onSave={onSave} />
  )
}

function StepDetailForm({
  step,
  value,
  onClose,
  onSave,
}: StepDetailModalProps & { step: CatalogueStep }) {
  const [draft, setDraft] = useState<LocalSchedule>(value)
  const fields = fieldsForStep(step.code)
  const derives = DERIVES_TO_EVENT[step.code]
  const set = (patch: Partial<LocalSchedule>) => setDraft((current) => ({ ...current, ...patch }))

  return (
    <Modal
      open
      onClose={onClose}
      title={step.name}
      subtitle={`${step.actor} · ${step.actions}`}
      width={620}
      footerNote="저장해도 이 브라우저에만 남습니다 (#213)"
      footer={
        <span className="flex gap-[8px]">
          <Button variant="secondary" onClick={onClose}>
            취소
          </Button>
          <Button onClick={() => onSave(draft)}>저장</Button>
        </span>
      }
    >
      <div className="flex flex-col gap-[16px]">
        <div className="flex flex-wrap gap-[14px]">
          <div className="min-w-[150px] flex-1">
            <Field label="시작일">
              <Input
                type="date"
                value={toDateInput(draft.startsAt)}
                onChange={(e) => set({ startsAt: fromDateInput(e.target.value) })}
              />
            </Field>
          </div>
          <div className="min-w-[150px] flex-1">
            <Field label="마감일">
              <Input
                type="date"
                value={toDateInput(draft.deadline)}
                onChange={(e) => set({ deadline: fromDateInput(e.target.value) })}
              />
            </Field>
          </div>
        </div>

        {fields.length === 0 ? (
          <p className="text-[12px] text-mute">
            이 단계는 일정 말고 고칠 것이 없어요. {step.actions}만 붙어 있습니다.
          </p>
        ) : (
          fields.map((spec) => (
            <DetailField
              key={spec.key}
              spec={spec}
              draft={draft}
              onChange={set}
              note={spec.kind === 'money' ? derives : undefined}
            />
          ))
        )}
      </div>
    </Modal>
  )
}

function DetailField({
  spec,
  draft,
  onChange,
  note,
}: {
  spec: FieldSpec
  draft: LocalSchedule
  onChange: (patch: Partial<LocalSchedule>) => void
  note?: string
}) {
  if (spec.kind === 'check') {
    return (
      <label className="flex items-center gap-[9px] text-[12.5px] font-bold text-ink2">
        <input
          type="checkbox"
          checked={draft.receiptRequired === true}
          onChange={(e) => onChange({ receiptRequired: e.target.checked })}
        />
        {spec.label}
        <span className="font-normal text-mute">영수증이 없으면 승인 요청을 만들지 않아요</span>
      </label>
    )
  }

  if (spec.kind === 'choice') {
    return (
      <Field label={spec.label}>
        <div className="flex gap-[7px]">
          {(['BATCH', 'EACH'] as const).map((mode) => (
            <Button
              key={mode}
              type="button"
              size="sm"
              variant={draft.approvalMode === mode ? 'primary' : 'secondary'}
              onClick={() => onChange({ approvalMode: mode })}
            >
              {mode === 'BATCH' ? '묶어서' : '건별'}
            </Button>
          ))}
        </div>
      </Field>
    )
  }

  if (spec.kind === 'date') {
    return (
      <Field label={spec.label}>
        <Input
          type="date"
          value={toDateInput(draft.dueDate)}
          onChange={(e) => onChange({ dueDate: fromDateInput(e.target.value) })}
        />
      </Field>
    )
  }

  if (spec.kind === 'money') {
    return (
      <Field label={spec.label} hint={note ?? '원'}>
        <Input
          type="number"
          min={0}
          step={1}
          inputMode="numeric"
          value={draft.amount ?? ''}
          onChange={(e) => onChange({ amount: e.target.value === '' ? null : Number(e.target.value) })}
        />
      </Field>
    )
  }

  const key = spec.key as 'title' | 'channel' | 'audience' | 'sendTiming' | 'vendor' | 'cancelTerms' | 'account'
  return (
    <Field label={spec.label} hint={spec.hint}>
      <Input
        value={draft[key] ?? ''}
        placeholder={spec.hint}
        onChange={(e) => onChange({ [key]: e.target.value })}
      />
    </Field>
  )
}
