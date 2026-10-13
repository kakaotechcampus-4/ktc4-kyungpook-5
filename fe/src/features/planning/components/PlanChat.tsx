// P1 왼쪽: 토리와 주고받는 대화. 저장하지 않는 임시 대화라 새로고침하면 사라진다.
import { useState } from 'react'
import type { ChatMessage } from '@/features/planning/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'

interface PlanChatProps {
  messages: ChatMessage[]
  onSend: (text: string) => void
}

export function PlanChat({ messages, onSend }: PlanChatProps) {
  const [draft, setDraft] = useState('')

  const send = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    onSend(trimmed)
    setDraft('')
  }

  // 빠른 답변은 마지막 토리 말풍선에만 남긴다. 지난 질문의 선택지는 이미 지나간 것이다.
  const lastToriId = [...messages].reverse().find((m) => m.from === '토리')?.id

  return (
    <Card className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-line px-[24px] py-[18px]">
        <h2 className="text-h2 text-ink">토리와 계획 잡기</h2>
        <span className="text-[11px] text-mute">저장되지 않는 임시 대화</span>
      </header>

      <div className="flex min-h-[420px] flex-col gap-[14px] px-[24px] pt-[20px] pb-[18px]">
        {messages.map((message) =>
          message.from === '토리' ? (
            <div key={message.id} className="flex flex-col gap-[9px]">
              <div className="flex items-start gap-[10px]">
                <Tori size={26} className="mt-[4px] shrink-0" />
                <p className="rounded-[12px] border border-line bg-bg px-[15px] py-[12px] text-[12.5px] leading-[19px] text-ink">
                  {message.text}
                </p>
              </div>
              {message.id === lastToriId && message.quickReplies && (
                <div className="flex flex-wrap gap-[8px] pl-[36px]">
                  {message.quickReplies.map((reply) => (
                    <button
                      key={reply}
                      type="button"
                      onClick={() => send(reply)}
                      className="rounded-[9px] border border-blue-200 bg-card px-[13px] py-[8px] text-[11.5px] font-bold text-blue-700 hover:bg-blue-50"
                    >
                      {reply}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p
              key={message.id}
              className={cn(
                'ml-auto max-w-[70%] rounded-[12px] bg-blue-600 px-[15px] py-[12px]',
                'text-[12.5px] leading-[19px] font-medium text-white',
              )}
            >
              {message.text}
            </p>
          ),
        )}
      </div>

      <form
        className="flex items-center gap-[10px] border-t border-line px-[20px] py-[16px]"
        onSubmit={(e) => {
          e.preventDefault()
          send(draft)
        }}
      >
        <div className="flex-1">
          <Input
            placeholder="답을 입력하세요"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </div>
        <Button type="submit">보내기</Button>
      </form>
    </Card>
  )
}
