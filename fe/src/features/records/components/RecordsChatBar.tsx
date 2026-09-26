// R1 하단 챗봇 바. 질문을 보내면 오른쪽 패널(R1-b)이 열린다.
import { useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

export function RecordsChatBar({
  pending,
  onAsk,
}: {
  pending: boolean
  onAsk: (question: string) => void
}) {
  const [question, setQuestion] = useState('')

  function submit() {
    if (!question.trim()) return
    onAsk(question)
    setQuestion('')
  }

  return (
    <Card className="flex w-full items-center gap-[10px] py-[11px] pr-[10px] pl-[18px]">
      <span className="size-[24px] shrink-0 rounded-[8px] bg-[#e6e6e6]" />
      <input
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => event.key === 'Enter' && submit()}
        placeholder="기록에 대해 물어보세요.  예) 작년 봄 MT 때 1인당 얼마 걷었어?"
        className="min-w-px flex-1 border-none text-[13px] text-[#262626] outline-none placeholder:text-[#8c8c8c]"
      />
      <p className="shrink-0 text-[11px] whitespace-nowrap text-[#8c8c8c]">
        저장되지 않는 일회성 대화
      </p>
      <Button size="pill" disabled={pending || !question.trim()} onClick={submit}>
        물어보기
      </Button>
    </Card>
  )
}
