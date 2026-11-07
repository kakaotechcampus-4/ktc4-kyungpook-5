// 단계 구성 편집. 13개 고정 카탈로그에서 넣고 빼고, 묶음 안의 순서를 바꾼다.
// 계획 검토 화면의 「준비 순서」 자리를 그대로 바꿔 쓰는 편집 모드이고, /planning/steps 주소도 이것을 그린다.
// 계획 중에만 들어올 수 있다 — 진행 중인 행사의 단계는 여기서 못 바꾼다.
//
// 일정·내용 수정은 여기서 하지 않는다. 구성은 넣고 빼기·순서만, 단계별 세부는 계획 검토에서 고친다.
import { useEffect, useRef, useState } from 'react'
import { DEMO_INCLUDED, STEP_CATALOGUE } from '@/features/planning/catalogue'
import { planningError } from '@/features/planning/errors'
import { planningApi } from '@/features/planning/api'
import {
  codesFromSteps,
  usePlanStepsSnapshot,
  useRequestPlanReview,
  useSavePlanSteps,
} from '@/features/planning/hooks'
import { ExcludedSteps } from '@/features/planning/components/ExcludedSteps'
import { StepBoard } from '@/features/planning/components/StepBoard'
import type { StepPhase } from '@/features/planning/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ErrorBanner } from '@/shared/ui/AuthShell'

export function StepComposer({
  eventId,
  demo = false,
  onDone,
}: {
  eventId: string | null
  demo?: boolean
  // 저장했거나 취소했을 때. 저장한 경우 saved가 true다.
  onDone: (saved: boolean) => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  // 서버가 만든 단계를 밑바탕으로 쓴다. 한 번 저장한 뒤로는 그 결과가 우선이다.
  const snapshot = usePlanStepsSnapshot(demo ? null : eventId)
  const save = useSavePlanSteps(eventId)
  const review = useRequestPlanReview(eventId)
  const serverSteps = snapshot.data?.steps
  // 편집을 시작할 때 본 계획 버전 (#177). baseRevision과 같은 스냅샷에서 읽으므로,
  // 저장이 성공했다면 이 값도 그때 최신이었다 — 저장 뒤 값이 커졌으면 실제로 바뀐 것이다.
  const entryPlanRevision = useRef<number | null>(null)

  // 포함한 단계의 코드. 배열 순서가 곧 묶음 안의 순서다.
  const [codes, setCodes] = useState<string[] | null>(demo ? Object.keys(DEMO_INCLUDED) : null)
  const [editingRevision, setEditingRevision] = useState<number | null>(null)
  const [saveError, setSaveError] = useState('')
  const resolved = codes ?? (serverSteps ? codesFromSteps(serverSteps) : null)
  const dates = Object.fromEntries(
    (serverSteps ?? []).map((step) => [
      step.code,
      { startsAt: step.startsAt, deadline: step.deadline },
    ]),
  )

  const current = resolved ?? []
  const editCodes = (update: (previous: string[]) => string[]) => {
    if (!demo && editingRevision === null && snapshot.data) {
      setEditingRevision(snapshot.data.baseRevision)
      entryPlanRevision.current = snapshot.data.planRevision
    }
    setCodes((previous) => update(previous ?? current))
  }
  const included = current
    .map((code) => STEP_CATALOGUE.find((s) => s.code === code))
    .filter((s) => s !== undefined)
  const excluded = STEP_CATALOGUE.filter((s) => !current.includes(s.code))
  // 저장하면 지워질 단계. 뺀 것이 있을 때만 저장 버튼 옆에 알린다.
  const removed = (serverSteps ?? []).filter((step) => !current.includes(step.code))
  const reloadLatest = async () => {
    await snapshot.refetch()
  }
  const saveSteps = async () => {
    if (!eventId) return onDone(false)
    if (
      removed.length &&
      !window.confirm(
        `${removed.map((step) => step.name).join(', ')} 단계를 빼면 해당 단계의 일정과 행동도 삭제됩니다. 저장할까요?`,
      )
    )
      return
    setSaveError('')
    const planRevisionBefore = entryPlanRevision.current ?? snapshot.data?.planRevision ?? null
    try {
      await save.mutateAsync({
        codes: current,
        expectedRevision: editingRevision ?? snapshot.data?.baseRevision ?? 0,
      })
    } catch (cause) {
      setSaveError(planningError(cause))
      return
    }
    // 바뀐 게 있을 때만 검토를 요청한다. 응답은 기다리지 않는다 — 계획 화면이 '검토 중'을 보여준다.
    try {
      const latest = await planningApi.stepsSnapshot(eventId)
      if (planRevisionBefore !== null && latest.planRevision > planRevisionBefore) {
        review.mutate(latest.planRevision)
      }
    } catch {
      // 단계 구성은 이미 저장됐다. 검토만 못 보낸 채 돌아가고, 계획 화면에서 「검토 받기」로 다시 요청한다.
    }
    onDone(true)
  }

  // 묶음 안에서만 자리를 바꾼다. 묶음 사이 이동은 카탈로그가 막는다.
  const reorder = (phase: StepPhase, from: number, to: number) =>
    editCodes((list) => {
      const inPhase = list.filter((c) => STEP_CATALOGUE.find((s) => s.code === c)?.phase === phase)
      const moved = [...inPhase]
      moved.splice(to, 0, ...moved.splice(from, 1))
      // 그 묶음 자리에 새 순서를 차례로 끼워 넣는다.
      let i = 0
      return list.map((code) =>
        STEP_CATALOGUE.find((s) => s.code === code)?.phase === phase ? moved[i++] : code,
      )
    })

  const ready = demo || (snapshot.data && !snapshot.isError)
  const localChanges = (() => {
    if (demo || !eventId) return false
    try {
      const value = localStorage.getItem('unyounghae_local_plan_v1')
      const raw = value ? JSON.parse(value)?.[eventId] : null
      return Boolean(raw && (raw.codes !== null || raw.started === true))
    } catch {
      return false
    }
  })()

  return (
    <fieldset
      disabled={save.isPending}
      className="grid min-w-0 grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_272px]"
    >
      <Card className="min-w-0 p-4 sm:p-6">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <h2 ref={heading} tabIndex={-1} className="text-h2 focus:outline-none">
            준비 순서 편집
          </h2>
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={save.isPending}
                onClick={() => onDone(false)}
              >
                변경 취소
              </Button>
              <Button
                size="sm"
                loading={save.isPending}
                disabled={
                  current.length === 0 ||
                  !!saveError ||
                  (!demo && (!snapshot.data || snapshot.isError))
                }
                onClick={() => void saveSteps()}
              >
                구성 저장
              </Button>
            </div>
            {removed.length > 0 && (
              <p className="text-right text-label text-pending">
                뺀 단계 {removed.length}개의 일정과 행동은 저장하면 지워져요.
              </p>
            )}
          </div>
        </div>

        <div className="mb-6 flex flex-col gap-4 empty:hidden">
          {!demo && eventId && snapshot.isPending && (
            <p role="status" className="text-caption text-mute">
              만들어진 단계를 불러오고 있어요.
            </p>
          )}
          {!demo && eventId && snapshot.isError && (
            <ErrorBanner
              title="행사 계획을 불러오지 못했어요."
              action={
                <Button variant="secondary" size="sm" onClick={() => void reloadLatest()}>
                  다시 불러오기
                </Button>
              }
            />
          )}
          {saveError && (
            <ErrorBanner
              title={saveError}
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setCodes(null)
                    setEditingRevision(null)
                    entryPlanRevision.current = null
                    setSaveError('')
                    void reloadLatest()
                  }}
                >
                  최신 내용으로 다시 시작
                </Button>
              }
            />
          )}
          {saveError && (
            <p className="text-caption text-mute">
              최신 내용으로 다시 시작하면 저장하지 않은 단계 구성은 사라집니다.
            </p>
          )}
          {!demo && !eventId && (
            <p role="alert" className="text-failed">
              어떤 행사의 단계인지 알 수 없어요. 계획 화면에서 다시 들어와 주세요.
            </p>
          )}
          {localChanges && (
            <details className="rounded-[10px] border border-line bg-bg px-4 py-3">
              <summary className="cursor-pointer font-bold text-ink2">
                이 브라우저에 저장된 이전 변경 보기
              </summary>
              <p className="mt-2 text-caption text-ink2">
                서버 저장으로 자동 전환하거나 덮어쓰지 않습니다. 필요한 내용을 확인한 뒤 다시 입력해
                주세요.
              </p>
            </details>
          )}
        </div>

        {ready && (
          <StepBoard
            included={included}
            schedule={demo ? DEMO_INCLUDED : {}}
            dates={demo ? undefined : dates}
            onReorder={reorder}
            onRemove={(code) => editCodes((list) => list.filter((c) => c !== code))}
          />
        )}
      </Card>
      <aside className="grid min-w-0 gap-4 xl:sticky xl:top-5">
        {ready && (
          <ExcludedSteps
            excluded={excluded}
            onInclude={(code) => editCodes((list) => [...list, code])}
          />
        )}
      </aside>
    </fieldset>
  )
}
