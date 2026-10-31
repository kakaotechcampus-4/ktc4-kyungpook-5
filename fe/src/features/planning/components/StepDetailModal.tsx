// 단계 세부 수정(#106). 일정은 Step, 나머지는 그 단계의 Action 에 저장된다.
// 밭 구성은 서버가 내려준 Action 의 type 이 정한다.
import { useState } from 'react'
import { useSaveStepDetail } from '@/features/planning/hooks'
import {
  amountLabel,
  DERIVES_TO_EVENT,
  fieldsForAction,
  type ActionPayload,
  type FieldSpec,
  type StepAction,
} from '@/features/planning/stepDetail'
import type { components } from '@/shared/api/schema'
import { ApiError } from '@/shared/api/types'
import { Field, ErrorBanner } from '@/shared/ui/AuthShell'
import { Button } from '@/shared/ui/Button'
import { Input } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'

type Step = components['schemas']['PlannedStepOut']

function saveErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    // 내가 보고 있는 동안 다른 사람이 고쳤다. 덮어쓰지 않고 다시 불러오게 한다.
    if (cause.code === 'VERSION_CONFLICT')
      return '내용이 그사이 바뀌었어요. 창을 닫고 다시 열어 주세요.'
    if (cause.code === 'NOT_EDITABLE') return '이미 끝난 내용이라 고칠 수 없어요.'
    return cause.message || '저장하지 못했어요.'
  }
  return '저장하지 못했어요. 연결 상태를 확인해 주세요.'
}

// <input type="date">는 yyyy-MM-dd만 받는다. 돌려줄 때는 그날 0시(한국)를 붙여
// 서버가 주는 ISO 와 같은 모양으로 맞춘다.
const toDateInput = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : '')
const fromDateInput = (value: string) => (value ? `${value}T00:00:00+09:00` : null)

interface Draft {
  startsAt: string | null
  deadline: string | null
  actions: Record<string, { title: string; amount: number | null; payload: ActionPayload }>
}

function toDraft(step: Step): Draft {
  return {
    startsAt: step.startsAt,
    deadline: step.deadline,
    actions: Object.fromEntries(
      step.actions.map((action) => [
        action.id,
        { title: action.title, amount: action.amount, payload: { ...action.payload } },
      ]),
    ),
  }
}

export function StepDetailModal({
  step,
  onClose,
  onSaved,
}: {
  step: Step | null
  onClose: () => void
  onSaved: () => void
}) {
  if (!step) return null
  return <StepDetailForm key={step.id} step={step} onClose={onClose} onSaved={onSaved} />
}

function StepDetailForm({
  step,
  onClose,
  onSaved,
}: {
  step: Step
  onClose: () => void
  onSaved: () => void
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(step))
  const [error, setError] = useState('')
  const save = useSaveStepDetail()
  const locked = !step.editable

  const submit = async () => {
    setError('')
    try {
      await save.mutateAsync({ step, draft })
      onSaved()
    } catch (cause) {
      setError(saveErrorMessage(cause))
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={step.name}
      subtitle={step.actions.map((action) => action.title).join(' · ') || '붙은 작업이 없어요'}
      width={620}
      footerNote={locked ? '이미 끝난 단계라 고칠 수 없어요' : undefined}
      footer={
        <span className="flex gap-[8px]">
          <Button variant="secondary" onClick={onClose}>
            {locked ? '닫기' : '취소'}
          </Button>
          {!locked && (
            <Button disabled={save.isPending} onClick={() => void submit()}>
              {save.isPending ? '저장하는 중…' : '저장'}
            </Button>
          )}
        </span>
      }
    >
      <div className="flex flex-col gap-[16px]">
        {error && <ErrorBanner title={error} />}

        <div className="flex flex-wrap gap-[14px]">
          <div className="min-w-[150px] flex-1">
            <Field label="시작일">
              <Input
                type="date"
                disabled={locked}
                value={toDateInput(draft.startsAt)}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, startsAt: fromDateInput(e.target.value) }))
                }
              />
            </Field>
          </div>
          <div className="min-w-[150px] flex-1">
            <Field label="마감일">
              <Input
                type="date"
                disabled={locked}
                value={toDateInput(draft.deadline)}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, deadline: fromDateInput(e.target.value) }))
                }
              />
            </Field>
          </div>
        </div>

        {step.actions.length === 0 ? (
          <p className="text-[12px] text-mute">
            이 단계에는 붙은 작업이 없어서 일정 말고 고칠 것이 없어요.
          </p>
        ) : (
          step.actions.map((action) => (
            <ActionFields
              key={action.id}
              action={action}
              stepCode={step.code}
              locked={locked || !action.editable}
              value={draft.actions[action.id]}
              onChange={(patch) =>
                setDraft((d) => ({
                  ...d,
                  actions: {
                    ...d.actions,
                    [action.id]: { ...d.actions[action.id], ...patch },
                  },
                }))
              }
            />
          ))
        )}
      </div>
    </Modal>
  )
}

function ActionFields({
  action,
  stepCode,
  locked,
  value,
  onChange,
}: {
  action: StepAction
  stepCode: string
  locked: boolean
  value: Draft['actions'][string]
  onChange: (patch: Partial<Draft['actions'][string]>) => void
}) {
  const fields = fieldsForAction(action)
  const derives = DERIVES_TO_EVENT[stepCode]
  const setPayload = (patch: Partial<ActionPayload>) =>
    onChange({ payload: { ...value.payload, ...patch } })

  return (
    <section className="flex flex-col gap-[12px] rounded-[11px] border border-line p-[14px]">
      <p className="text-[11px] font-bold text-mute">
        {action.type}
        {locked && ' · 승인이 끝나 고칠 수 없어요'}
      </p>

      <Field label="제목">
        <Input
          disabled={locked}
          value={value.title}
          onChange={(e) => onChange({ title: e.target.value })}
        />
      </Field>

      {/* 금액이 없는 유형에는 금액 칸을 그리지 않는다. 서버가 null 로 둔 채 쓰지 않는다 */}
      {(action.amount !== null || stepCode in DERIVES_TO_EVENT) && (
        <Field label={amountLabel(stepCode)} hint={derives ?? '원'}>
          <Input
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
            disabled={locked}
            value={value.amount ?? ''}
            onChange={(e) =>
              onChange({ amount: e.target.value === '' ? null : Number(e.target.value) })
            }
          />
        </Field>
      )}

      {fields.map((spec) => (
        <PayloadField
          key={spec.key}
          spec={spec}
          locked={locked}
          payload={value.payload}
          onChange={setPayload}
        />
      ))}
    </section>
  )
}

function PayloadField({
  spec,
  locked,
  payload,
  onChange,
}: {
  spec: FieldSpec
  locked: boolean
  payload: ActionPayload
  onChange: (patch: Partial<ActionPayload>) => void
}) {
  if (spec.kind === 'check') {
    return (
      <label className="flex items-center gap-[9px] text-[12.5px] font-bold text-ink2">
        <input
          type="checkbox"
          disabled={locked}
          checked={payload.receiptRequired === true}
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
              disabled={locked}
              variant={payload.approvalMode === mode ? 'primary' : 'secondary'}
              onClick={() => onChange({ approvalMode: mode })}
            >
              {mode === 'BATCH' ? '묶어서' : '건별'}
            </Button>
          ))}
        </div>
      </Field>
    )
  }

  const key = spec.key as 'channel' | 'audience' | 'sendTiming' | 'vendor' | 'cancelTerms' | 'account'
  return (
    <Field label={spec.label} hint={spec.hint}>
      <Input
        disabled={locked}
        placeholder={spec.hint}
        value={payload[key] ?? ''}
        onChange={(e) => onChange({ [key]: e.target.value })}
      />
    </Field>
  )
}
