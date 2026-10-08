// 행사 계획. 1단계에서 토리와 큰 틀을 잡고, 2단계에서 단계 흐름을 확인하고 시작한다.
// 두 단계 사이에 계획을 만드는 화면이 끼어든다.
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { PlanStepper } from '@/features/planning/components/PlanStepper'
import { PlanSummaryPanel } from '@/features/planning/components/PlanSummaryPanel'
import { StepFlow } from '@/features/planning/components/StepFlow'
import {
  DEMO_FACTS,
  DEMO_MESSAGES,
  DEMO_PLAN_META,
  DEMO_PLAN_STEPS,
  DEMO_REFERENCE,
  DEMO_SUMMARY,
  DEMO_WARNING,
  EMPTY_SUMMARY,
  FIRST_MESSAGE,
  PLAN_STEPS,
} from '@/features/planning/mock'
import type { ChatMessage } from '@/features/planning/types'
import { Button } from '@/shared/ui/Button'
import { PlanGeneratingScreen } from '@/shared/ui/StateScreen'

// 계획을 만드는 데 걸리는 시간. 서버가 붙으면 응답을 기다리는 것으로 바뀐다.
const GENERATING_MS = 1600

export default function PlanningPage() {
  const navigate = useNavigate()
  // 다른 화면과 같은 방식. ?demo면 대화가 오간 뒤 상태를, 없으면 첫 질문만 보인다.
  const demo = useSearchParams()[0].has('demo')

  const [step, setStep] = useState<1 | 2>(1)
  const [messages, setMessages] = useState<ChatMessage[]>(demo ? DEMO_MESSAGES : [FIRST_MESSAGE])
  const [generating, setGenerating] = useState(false)

  // TODO(연동): POST /plans. 응답이 오면 2단계로 간다. 지금은 화면 흐름만 잇는다.
  useEffect(() => {
    if (!generating) return
    const timer = setTimeout(() => {
      setGenerating(false)
      setStep(2)
    }, GENERATING_MS)
    return () => clearTimeout(timer)
  }, [generating])

  // TODO(연동): POST /plans/chat. 토리의 답과 「정한 것」 갱신은 서버가 준다.
  const send = (text: string) =>
    setMessages((list) => [...list, { id: `msg_${list.length}`, from: '나', text }])

  if (generating) {
    return (
      <PlanGeneratingScreen steps={PLAN_STEPS} current={0} onCancel={() => setGenerating(false)} />
    )
  }

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex items-start justify-between gap-[16px]">
        <div className="flex flex-col gap-[4px]">
          <h1 className="text-h1">행사 계획</h1>
          <p className="text-mute">
            {step === 1
              ? '토리와 대화하면서 큰 틀을 잡습니다. 정해진 건 오른쪽에 쌓입니다.'
              : demo
                ? DEMO_PLAN_META
                : '행사 이름 · 인원 · 예산 · 기간'}
          </p>
        </div>
        {step === 2 && (
          <div className="flex gap-[9px]">
            <Button variant="secondary" onClick={() => setStep(1)}>
              1단계로 돌아가기
            </Button>
            {/* TODO(연동): PATCH /plans/{id} 로 임시 저장한다. */}
            <Button variant="secondary">임시 저장</Button>
          </div>
        )}
      </header>

      <PlanStepper current={step} />

      {step === 1 ? (
        <div className="flex items-start gap-[20px]">
          <PlanChat messages={messages} onSend={send} />
          <PlanFacts
            facts={demo ? DEMO_FACTS : {}}
            reference={demo ? DEMO_REFERENCE : undefined}
            onNext={() => setGenerating(true)}
          />
        </div>
      ) : (
        <div className="flex items-start gap-[20px]">
          {/* TODO: 단계 세부 수정 모달은 P2-b와 함께 붙인다. */}
          <StepFlow steps={demo ? DEMO_PLAN_STEPS : []} onEditStep={() => {}} />
          <PlanSummaryPanel
            summary={demo ? DEMO_SUMMARY : EMPTY_SUMMARY}
            warning={demo ? DEMO_WARNING : undefined}
            onFixSteps={() => {}}
            // TODO(연동): POST /events. 지금은 행사 목록으로만 보낸다.
            onStart={() => navigate('/events')}
          />
        </div>
      )}
    </div>
  )
}
