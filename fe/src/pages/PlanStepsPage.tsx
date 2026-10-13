// P2-b 단계 수정. 13개 고정 카탈로그에서 넣고 빼고, 묶음 안의 순서를 바꾼다.
// 계획 중에만 들어올 수 있다 — 진행 중인 행사의 단계는 여기서 못 바꾼다.
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { DEMO_INCLUDED, STEP_CATALOGUE } from '@/features/planning/catalogue'
import { ExcludedSteps } from '@/features/planning/components/ExcludedSteps'
import { StepBoard } from '@/features/planning/components/StepBoard'
import type { StepPhase } from '@/features/planning/types'
import { Button } from '@/shared/ui/Button'

export default function PlanStepsPage() {
  const navigate = useNavigate()
  // 다른 화면과 같은 방식. ?demo면 10개가 들어간 상태를, 없으면 아무것도 안 넣은 상태를 보인다.
  const demo = useSearchParams()[0].has('demo')

  // 포함한 단계의 코드. 배열 순서가 곧 묶음 안의 순서다.
  const [codes, setCodes] = useState<string[]>(demo ? Object.keys(DEMO_INCLUDED) : [])

  const included = codes
    .map((code) => STEP_CATALOGUE.find((s) => s.code === code))
    .filter((s) => s !== undefined)
  const excluded = STEP_CATALOGUE.filter((s) => !codes.includes(s.code))

  // 묶음 안에서만 자리를 바꾼다. 묶음 사이 이동은 카탈로그가 막는다.
  const reorder = (phase: StepPhase, from: number, to: number) =>
    setCodes((list) => {
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
          <p className="text-mute">13개 중 {codes.length}개 포함 · 계획 중에만 바꿀 수 있어요</p>
        </div>
        <div className="flex gap-[9px]">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            취소
          </Button>
          {/* TODO(연동): PATCH /plans/{id}/steps */}
          <Button disabled={codes.length === 0} onClick={() => navigate(-1)}>
            저장
          </Button>
        </div>
      </header>

      <div className="flex items-start gap-[20px]">
        <StepBoard
          included={included}
          schedule={DEMO_INCLUDED}
          onReorder={reorder}
          onRemove={(code) => setCodes((list) => list.filter((c) => c !== code))}
        />
        <ExcludedSteps
          excluded={excluded}
          onInclude={(code) => setCodes((list) => [...list, code])}
        />
      </div>
    </div>
  )
}
