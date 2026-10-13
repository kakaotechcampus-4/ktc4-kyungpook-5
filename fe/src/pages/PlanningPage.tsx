// P1 행사 계획 1단계. 토리와 대화하면서 큰 틀을 잡고, 정해진 건 오른쪽에 쌓인다.
// 2단계(흐름 만들기)는 #82에서 채운다. 지금은 계획을 만드는 화면까지 이어 둔다.
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { PlanStepper } from '@/features/planning/components/PlanStepper'
import {
  DEMO_FACTS,
  DEMO_MESSAGES,
  DEMO_REFERENCE,
  FIRST_MESSAGE,
  PLAN_STEPS,
} from '@/features/planning/mock'
import type { ChatMessage } from '@/features/planning/types'
import { PlanGeneratingScreen } from '@/shared/ui/StateScreen'

export default function PlanningPage() {
  // 다른 화면과 같은 방식. ?demo면 대화가 오간 뒤 상태를, 없으면 첫 질문만 보인다.
  const demo = useSearchParams()[0].has('demo')

  const [messages, setMessages] = useState<ChatMessage[]>(demo ? DEMO_MESSAGES : [FIRST_MESSAGE])
  const [generating, setGenerating] = useState(false)

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
      <header className="flex flex-col gap-[4px]">
        <h1 className="text-h1">행사 계획</h1>
        <p className="text-mute">
          토리와 대화하면서 큰 틀을 잡습니다. 정해진 건 오른쪽에 쌓입니다.
        </p>
      </header>

      <PlanStepper current={1} />

      <div className="flex items-start gap-[20px]">
        <PlanChat messages={messages} onSend={send} />
        <PlanFacts
          facts={demo ? DEMO_FACTS : {}}
          reference={demo ? DEMO_REFERENCE : undefined}
          onNext={() => setGenerating(true)}
        />
      </div>
    </div>
  )
}
