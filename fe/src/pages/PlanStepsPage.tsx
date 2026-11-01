// P2-b 단계 수정. 13개 고정 카탈로그에서 넣고 빼고, 묶음 안의 순서를 바꾼다.
// 계획 중에만 들어올 수 있다 — 진행 중인 행사의 단계는 여기서 못 바꾼다.
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { DEMO_INCLUDED, STEP_CATALOGUE } from '@/features/planning/catalogue'
import { planningError } from '@/features/planning/errors'
import { codesFromSteps, usePlanRevision, usePlanSteps, useSavePlanSteps } from '@/features/planning/hooks'
import { ExcludedSteps } from '@/features/planning/components/ExcludedSteps'
import { StepBoard } from '@/features/planning/components/StepBoard'
import { StepDetailModal } from '@/features/planning/components/StepDetailModal'
import type { StepPhase } from '@/features/planning/types'
import { Button } from '@/shared/ui/Button'
import { ErrorBanner } from '@/shared/ui/AuthShell'

export default function PlanStepsPage() {
  const navigate = useNavigate()
  // 다른 화면과 같은 방식. ?demo면 10개가 들어간 상태를, 없으면 아무것도 안 넣은 상태를 보인다.
  const params = useSearchParams()[0]
  const demo = params.has('demo')
  const eventId = params.get('eventId')

  // 서버가 만든 단계를 밑바탕으로 쓴다. 한 번 저장한 뒤로는 그 결과가 우선이다.
  const serverSteps = usePlanSteps(demo ? null : eventId)
  const save = useSavePlanSteps(eventId)
  const screen = usePlanRevision(demo ? null : eventId)

  // 포함한 단계의 코드. 배열 순서가 곧 묶음 안의 순서다.
  const [codes, setCodes] = useState<string[] | null>(demo ? Object.keys(DEMO_INCLUDED) : null)
  const [editing, setEditing] = useState<string | null>(null)
  const [saveError, setSaveError] = useState('')
  const resolved =
    codes ?? (serverSteps.data ? codesFromSteps(serverSteps.data) : null)
  // 일정은 서버가 들고 있다. 화면에는 StepCode 로 찾아 쓴다.
  const byCode = new Map<string, (typeof serverSteps.data & object)[number]>(
    (serverSteps.data ?? []).map((step) => [step.code, step]),
  )
  const dates = Object.fromEntries(
    (serverSteps.data ?? []).map((step) => [
      step.code,
      { startsAt: step.startsAt, deadline: step.deadline },
    ]),
  )

  const current = resolved ?? []
  const included = current
    .map((code) => STEP_CATALOGUE.find((s) => s.code === code))
    .filter((s) => s !== undefined)
  const excluded = STEP_CATALOGUE.filter((s) => !current.includes(s.code))
  const reloadLatest = async () => {
    setSaveError('')
    await Promise.all([serverSteps.refetch(), screen.refetch()])
  }
  const saveSteps = async () => {
    if (!eventId) return navigate(-1)
    setSaveError('')
    try {
      await save.mutateAsync({
        codes: current,
        expectedRevision: screen.data?.baseRevision ?? 0,
      })
      navigate(-1)
    } catch (cause) {
      setSaveError(planningError(cause))
      await reloadLatest()
    }
  }

  // 묶음 안에서만 자리를 바꾼다. 묶음 사이 이동은 카탈로그가 막는다.
  const reorder = (phase: StepPhase, from: number, to: number) =>
    setCodes((previous) => {
      const list = previous ?? current
      const inPhase = list.filter((c) => STEP_CATALOGUE.find((s) => s.code === c)?.phase === phase)
      const moved = [...inPhase]
      moved.splice(to, 0, ...moved.splice(from, 1))
      // 그 묶음 자리에 새 순서를 차례로 끼워 넣는다.
      let i = 0
      return list.map((code) =>
        STEP_CATALOGUE.find((s) => s.code === code)?.phase === phase ? moved[i++] : code,
      )
    })

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex items-start justify-between gap-[16px]">
        <div className="flex flex-col gap-[4px]">
          <h1 className="text-h1">단계 수정</h1>
          <p className="text-mute">
            13개 중 {current.length}개 포함 · 계획 중에만 바꿀 수 있어요
          </p>
        </div>
        <div className="flex gap-[9px]">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            취소
          </Button>
          <Button
            disabled={current.length === 0 || save.isPending || (!demo && (!serverSteps.data || !screen.data))}
            onClick={() => void saveSteps()}
          >
            {save.isPending ? '저장하는 중…' : '저장'}
          </Button>
        </div>
      </header>

      {!demo && eventId && serverSteps.isPending && (
        <p role="status" className="text-mute">
          만들어진 단계를 불러오고 있어요.
        </p>
      )}
      {saveError && (
        <ErrorBanner
          title={saveError}
          action={
            <Button variant="secondary" size="sm" onClick={() => void reloadLatest()}>
              최신 내용 다시 불러오기
            </Button>
          }
        />
      )}
      {!demo && !eventId && (
        <p role="alert" className="text-failed">
          어떤 행사의 단계인지 알 수 없어요. 계획 화면에서 다시 들어와 주세요.
        </p>
      )}
      {!demo && eventId && (
        <>
          <p className="text-mute">
            저장하면 행사 계획에 반영되고, 다른 화면에서도 같은 구성을 봅니다.
          </p>
          {(() => {
            const raw = (() => {
              try {
                const value = localStorage.getItem('unyounghae_local_plan_v1')
                return value ? JSON.parse(value)?.[eventId] : null
              } catch {
                return null
              }
            })()
            const hasLocalChanges = raw && (raw.codes !== null || raw.started === true)
            if (!hasLocalChanges) return null
            return (
              <details className="rounded-[10px] border border-line bg-bg px-4 py-3">
                <summary className="cursor-pointer font-bold text-ink2">
                  이 브라우저에 저장된 이전 변경 보기
                </summary>
                <p className="mt-2 text-caption text-ink2">
                  서버 저장으로 자동 전환하거나 덮어쓰지 않습니다. 필요한 내용을 확인한 뒤 다시 입력해 주세요.
                </p>
              </details>
            )
          })()}
        </>
      )}

      <div className="flex items-start gap-[20px]">
        <StepBoard
          included={included}
          schedule={DEMO_INCLUDED}
          dates={demo ? undefined : dates}
          onEditDetail={demo ? undefined : setEditing}
          onReorder={reorder}
          onRemove={(code) => setCodes((list) => (list ?? current).filter((c) => c !== code))}
        />
        <ExcludedSteps
          excluded={excluded}
          onInclude={(code) => setCodes((list) => [...(list ?? current), code])}
        />
      </div>

      <StepDetailModal
        step={editing ? (byCode.get(editing) ?? null) : null}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          void serverSteps.refetch()
        }}
        onReload={() => {
          setEditing(null)
          void reloadLatest()
        }}
      />
    </div>
  )
}
