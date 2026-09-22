// P1 1단계 대화. 말풍선 목록(PlanChatCard)과 하단 입력 바(PlanChatBar).
import { useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { EVENT_TYPE_LABEL } from '@/features/planning/labels'
import type { PlanChatTurn } from '@/features/planning/types'

interface PlanChatCardProps {
  turns: PlanChatTurn[]
  // 서버가 "2단계로 넘어가도 된다"고 판단한 상태. 마지막 답변에만 버튼이 붙는다.
  readyToGenerate: boolean
  pending: boolean
  generating: boolean
  onAsk: (content: string) => void
  onGenerate: () => void
}

function AssistantTurn({
  turn,
  onAsk,
  children,
}: {
  turn: PlanChatTurn
  onAsk: (content: string) => void
  children?: React.ReactNode
}) {
  return (
    <div className="flex w-full items-start gap-[10px]">
      <span className="size-[26px] shrink-0 rounded-[9px] bg-[#333]" />
      <div className="flex max-w-[560px] flex-col gap-[8px] rounded-[14px] bg-[#f7f7f7] px-[16px] py-[13px]">
        <p className="text-[13px] text-[#383838]">{turn.content}</p>

        {turn.quickReplies && (
          <div className="flex flex-wrap items-start gap-[6px]">
            {turn.quickReplies.map((type) => (
              <Button
                key={type}
                variant="secondary"
                size="pill"
                onClick={() => onAsk(EVENT_TYPE_LABEL[type])}
              >
                {EVENT_TYPE_LABEL[type]}
              </Button>
            ))}
          </div>
        )}

        {turn.reference && (
          <div className="flex w-full flex-col gap-[5px] rounded-[10px] border border-[#e0e0e0] bg-white px-[14px] py-[12px]">
            <p className="text-[10.5px] font-medium text-[#737373]">{turn.reference.title}</p>
            {turn.reference.rows.map(([label, value]) => (
              <div key={label} className="flex w-full items-start gap-[8px] text-[11.5px]">
                <p className="w-[80px] shrink-0 text-[#808080]">{label}</p>
                <p className="font-medium text-[#383838]">{value}</p>
              </div>
            ))}
          </div>
        )}

        {children}
      </div>
    </div>
  )
}

export function PlanChatCard({
  turns,
  readyToGenerate,
  pending,
  generating,
  onAsk,
  onGenerate,
}: PlanChatCardProps) {
  // "더 이야기할게요"를 누르면 버튼만 접고 대화를 이어 간다.
  const [ctaHidden, setCtaHidden] = useState(false)
  const lastTurn = turns[turns.length - 1]
  const showCta = readyToGenerate && !ctaHidden && !pending && lastTurn?.role === 'ASSISTANT'

  return (
    <Card className="flex min-w-px flex-1 flex-col gap-[16px] rounded-[20px] p-[24px]">
      {turns.map((turn, index) =>
        turn.role === 'USER' ? (
          <div key={turn.id} className="flex w-full items-start">
            <div className="h-px flex-1" />
            <div className="max-w-[460px] rounded-[14px] bg-[#292929] px-[16px] py-[13px]">
              <p className="text-[13px] text-[#f7f7f7]">{turn.content}</p>
            </div>
          </div>
        ) : (
          <AssistantTurn key={turn.id} turn={turn} onAsk={onAsk}>
            {index === turns.length - 1 && showCta && (
              <div className="flex items-start gap-[8px]">
                <Button size="pill" disabled={generating} onClick={onGenerate}>
                  {generating ? '단계를 배열하는 중…' : '다음 단계로'}
                </Button>
                <Button variant="secondary" size="pill" onClick={() => setCtaHidden(true)}>
                  더 이야기할게요
                </Button>
              </div>
            )}
          </AssistantTurn>
        ),
      )}

      {pending && <p className="text-[11.5px] text-[#8c8c8c]">정리하는 중입니다…</p>}
      {generating && (
        <p className="text-[11.5px] text-[#8c8c8c]">
          대화를 근거로 단계와 행동을 만들고 있습니다. 조금 걸릴 수 있습니다.
        </p>
      )}
    </Card>
  )
}

export function PlanChatBar({
  pending,
  onAsk,
}: {
  pending: boolean
  onAsk: (content: string) => void
}) {
  const [text, setText] = useState('')

  function submit() {
    if (!text.trim()) return
    onAsk(text)
    setText('')
  }

  return (
    <Card className="flex w-full items-center gap-[10px] rounded-[16px] py-[10px] pr-[10px] pl-[18px]">
      <span className="size-[24px] shrink-0 rounded-[8px] bg-[#e6e6e6]" />
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => event.key === 'Enter' && submit()}
        placeholder="무엇이든 물어보거나 고쳐달라고 하세요.  예) 인원 40명으로 바꿔줘"
        className="min-w-px flex-1 border-none text-[13px] text-[#262626] outline-none placeholder:text-[#8c8c8c]"
      />
      <Button size="pill" disabled={pending || !text.trim()} onClick={submit}>
        보내기
      </Button>
    </Card>
  )
}
