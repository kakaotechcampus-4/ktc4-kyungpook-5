// R1-b 챗봇 패널. 대화는 저장되지 않으므로 여기서만 산다.
import { useState } from 'react'
import { Button } from '@/shared/ui/Button'
import type { ChatTurn } from '@/features/records/types'

interface RecordsChatPanelProps {
  turns: ChatTurn[]
  suggestions: string[]
  pending: boolean
  onAsk: (question: string) => void
  onClose: () => void
}

function AssistantTurn({ turn }: { turn: ChatTurn }) {
  return (
    <div className="flex w-full items-start gap-[9px]">
      <span className="size-[24px] shrink-0 rounded-[8px] bg-[#333]" />
      <div className="flex min-w-px flex-1 flex-col gap-[9px] rounded-[14px] bg-[#f7f7f7] px-[14px] py-[12px]">
        <p className="text-[12.5px] text-[#383838]">{turn.content}</p>

        {turn.sources && turn.sources.length > 0 && (
          <div className="flex w-full flex-col gap-[5px] rounded-[9px] border border-[#e3e3e3] bg-white px-[11px] py-[9px]">
            <p className="text-[10px] font-medium text-[#737373]">근거로 쓴 기록</p>
            {turn.sources.map((source) => (
              <div
                key={`${source.recordId}-${source.location.label}`}
                className="flex w-full items-center gap-[6px]"
              >
                <span className="h-[14px] w-[12px] shrink-0 rounded-[3px] bg-[#e6e6e6]" />
                <p className="min-w-px truncate text-[10.5px] font-medium text-[#404040]">
                  {source.fileName}
                </p>
                <div className="h-px flex-1" />
                <p className="shrink-0 text-[10px] whitespace-nowrap text-[#808080]">
                  {source.location.label}
                </p>
              </div>
            ))}
          </div>
        )}

        {turn.notFound && (
          <div className="flex w-full flex-col gap-[3px] rounded-[9px] border border-[#e3e3e3] bg-white px-[11px] py-[9px]">
            <p className="text-[10px] font-medium text-[#737373]">기록에 없는 것</p>
            <p className="text-[11px] text-[#666]">{turn.notFound}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export function RecordsChatPanel({
  turns,
  suggestions,
  pending,
  onAsk,
  onClose,
}: RecordsChatPanelProps) {
  const [question, setQuestion] = useState('')

  function submit() {
    if (!question.trim()) return
    onAsk(question)
    setQuestion('')
  }

  return (
    <aside className="sticky top-0 flex h-screen w-[380px] shrink-0 flex-col border-l border-[#e6e6e6] bg-white">
      <div className="flex w-full items-center gap-[10px] px-[20px] py-[16px]">
        <p className="text-[14.5px] font-semibold text-[#242424]">기록에게 묻기</p>
        <div className="h-px flex-1" />
        <button
          type="button"
          onClick={onClose}
          aria-label="패널 닫기"
          className="text-[13px] font-medium text-[#737373] hover:text-[#333]"
        >
          ✕
        </button>
      </div>

      <p className="border-t border-[#ededed] bg-[#f8f8f8] px-[20px] py-[11px] text-[11px] text-[#737373]">
        이 대화는 페이지를 벗어나면 사라집니다. 저장되지 않습니다.
      </p>

      <div className="flex min-h-px w-full flex-1 flex-col gap-[16px] overflow-y-auto px-[20px] py-[18px]">
        {turns.map((turn, index) =>
          turn.role === 'USER' ? (
            <div key={index} className="flex w-full items-start">
              <div className="h-px flex-1" />
              <div className="max-w-[268px] rounded-[14px] bg-[#292929] px-[14px] py-[11px]">
                <p className="text-[12.5px] text-[#f7f7f7]">{turn.content}</p>
              </div>
            </div>
          ) : (
            <AssistantTurn key={index} turn={turn} />
          ),
        )}

        {pending && <p className="text-[11.5px] text-[#8c8c8c]">기록을 찾아보는 중입니다…</p>}

        {suggestions.length > 0 && (
          <div className="flex w-full flex-col gap-[7px]">
            <p className="text-[10.5px] font-medium text-[#737373]">이어서 물어볼 만한 것</p>
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => onAsk(suggestion)}
                className="w-full rounded-[16px] border border-[#dedede] bg-white px-[11px] py-[8px] text-left text-[11px] text-[#595959] hover:bg-[#f7f7f7]"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex w-full items-center gap-[8px] border-t border-[#ededed] py-[11px] pr-[10px] pl-[16px]">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && submit()}
          placeholder="기록에 대해 물어보세요"
          className="min-w-px flex-1 border-none text-[12.5px] text-[#262626] outline-none placeholder:text-[#8c8c8c]"
        />
        <Button size="pill" disabled={pending || !question.trim()} onClick={submit}>
          보내기
        </Button>
      </div>
    </aside>
  )
}
