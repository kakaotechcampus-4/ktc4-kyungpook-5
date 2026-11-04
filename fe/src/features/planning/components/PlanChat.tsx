// P1 왼쪽: 토리와 주고받는 대화.
import { useLayoutEffect, useRef, useState } from 'react'
import type { ChatMessage, PlanProgress } from '@/features/planning/types'
import { isSendKey } from '@/features/planning/chatKey'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Textarea } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'

interface PlanChatProps {
  messages: ChatMessage[]
  onSend: (text: string) => Promise<boolean>
  demo?: boolean
  persisted?: boolean
  initialDraft?: string
  busy?: boolean
  error?: string
  // 스트림으로 받는 동안의 임시 표시(#285). 보낸 말, 진행 줄, 흘러나오는 토리 답변.
  pendingText?: string
  progress?: PlanProgress[]
  pendingReply?: string
  notice?: string
}

// 진행 중은 도는 원, 완료는 초록 체크, 실패는 느낌표. 움직임 줄이기 설정이면 돌지 않는다.
function ProgressIcon({ status }: { status: PlanProgress['status'] }) {
  if (status === 'running')
    return (
      <svg
        aria-hidden
        viewBox="0 0 16 16"
        className="size-[14px] shrink-0 animate-spin text-blue-600 motion-reduce:animate-none"
        fill="none"
      >
        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.25" />
        <path d="M8 2a6 6 0 0 1 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  if (status === 'completed')
    return (
      <svg aria-hidden viewBox="0 0 16 16" className="size-[14px] shrink-0 text-done" fill="none">
        <circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.15" />
        <path
          d="M4.5 8.2 7 10.6l4.5-5"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  return (
    <span aria-hidden className="w-[14px] shrink-0 text-center font-bold text-failed">
      !
    </span>
  )
}

export function PlanChat({
  messages,
  onSend,
  busy = false,
  error = '',
  pendingText = '',
  progress = [],
  pendingReply = '',
  notice = '',
  demo = false,
  persisted = false,
  initialDraft = '',
}: PlanChatProps) {
  const [draft, setDraft] = useState(initialDraft)
  const scrollRef = useRef<HTMLDivElement>(null)
  const followEnd = useRef(true)
  useLayoutEffect(() => {
    const panel = scrollRef.current
    if (panel && followEnd.current) panel.scrollTop = panel.scrollHeight
  }, [messages, pendingText, progress, pendingReply])

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    setDraft(trimmed)
    if (await onSend(trimmed)) setDraft('')
  }

  // 빠른 답변은 마지막 토리 말풍선에만 남긴다. 지난 질문의 선택지는 이미 지나간 것이다.
  const lastToriId = [...messages].reverse().find((m) => m.from === '토리')?.id

  return (
    <Card className="flex h-[min(70vh,700px)] min-h-[380px] w-full min-w-0 flex-col lg:flex-1">
      <header className="flex items-center justify-between border-b border-line px-[24px] py-[18px]">
        <h2 className="text-h2 text-ink">토리와 계획 잡기</h2>
        <span className="text-[11px] text-mute">
          {demo
            ? '화면 미리보기'
            : persisted
              ? '저장된 대화'
              : '첫 메시지를 보내면 계획이 만들어져요'}
        </span>
      </header>

      <div
        ref={scrollRef}
        role="region"
        aria-label="계획 대화 내용"
        tabIndex={0}
        onScroll={(event) => {
          const panel = event.currentTarget
          followEnd.current = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 48
        }}
        className="flex min-h-0 flex-1 flex-col gap-[14px] overflow-y-auto px-[24px] pt-[20px] pb-[18px]"
      >
        {messages.map((message) =>
          message.from === '토리' ? (
            <div key={message.id} className="flex flex-col gap-[9px]">
              <div className="flex items-start gap-[10px]">
                <Tori size={26} className="mt-[4px] shrink-0" />
                <p className="rounded-[12px] border border-line bg-bg px-[15px] py-[12px] text-[12.5px] leading-[19px] whitespace-pre-wrap text-ink">
                  {message.text}
                </p>
              </div>
              {message.id === lastToriId && message.quickReplies && (
                <div className="flex flex-wrap gap-[8px] pl-[36px]">
                  {message.quickReplies.map((reply) => (
                    <button
                      key={reply}
                      type="button"
                      disabled={busy}
                      onClick={() => void send(reply)}
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
                'text-[12.5px] leading-[19px] font-medium whitespace-pre-wrap text-white',
              )}
            >
              {message.text}
            </p>
          ),
        )}
        {busy && pendingText && (
          <p className="ml-auto max-w-[70%] rounded-[12px] bg-blue-600 px-[15px] py-[12px] text-[12.5px] leading-[19px] font-medium whitespace-pre-wrap text-white opacity-80">
            {pendingText}
          </p>
        )}
        {busy && progress.length > 0 && (
          <ul aria-label="처리 단계" className="flex flex-col gap-[6px] pl-[36px]">
            {progress.map((line) => (
              <li
                key={line.operationId}
                className={cn(
                  'flex items-center gap-[8px] text-[12px] leading-[18px]',
                  line.status === 'failed' ? 'text-failed' : 'text-ink2',
                )}
              >
                <ProgressIcon status={line.status} />
                <span>{line.text}</span>
              </li>
            ))}
          </ul>
        )}
        {busy && pendingReply && (
          <div className="flex items-start gap-[10px]">
            <Tori size={26} className="mt-[4px] shrink-0" />
            <p className="rounded-[12px] border border-line bg-bg px-[15px] py-[12px] text-[12.5px] leading-[19px] whitespace-pre-wrap text-ink">
              {pendingReply}
            </p>
          </div>
        )}
      </div>

      {busy && (
        // 화면 낭독기는 진행 줄 변화를 여기서 한 번에 듣는다. 답변 조각마다 읽지 않는다.
        // 진행 줄·답변이 보이면 같은 글을 두 번 보이지 않게 화면에서는 숨긴다.
        <p
          role="status"
          className={cn(
            'px-[24px] text-mute',
            !notice && (progress.length > 0 || pendingReply) && 'sr-only',
          )}
        >
          {notice ||
            (pendingReply
              ? '토리가 답변을 쓰고 있어요…'
              : progress.at(-1)?.text ?? '토리가 답변을 준비하고 있어요…')}
        </p>
      )}
      {error && (
        <p role="alert" className="px-[24px] text-failed">
          {error}
        </p>
      )}
      <form
        className="flex items-center gap-[10px] border-t border-line px-[20px] py-[16px]"
        onSubmit={(e) => {
          e.preventDefault()
          void send(draft)
        }}
      >
        <div className="min-w-0 flex-1">
          <Textarea
            aria-label="계획 대화 답변"
            aria-describedby="planning-input-help"
            rows={2}
            className="min-h-[58px] max-h-[160px] resize-y"
            disabled={busy}
            placeholder="답을 입력하세요"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (
                !isSendKey({
                  key: e.key,
                  shiftKey: e.shiftKey,
                  altKey: e.altKey,
                  ctrlKey: e.ctrlKey,
                  metaKey: e.metaKey,
                  isComposing: e.nativeEvent.isComposing,
                  keyCode: e.keyCode,
                })
              )
                return
              e.preventDefault()
              if (!e.repeat) e.currentTarget.form?.requestSubmit()
            }}
          />
          <p id="planning-input-help" className="mt-1 text-[11px] text-mute">
            Enter로 전송 · Shift+Enter로 줄바꿈
          </p>
        </div>
        <Button type="submit" loading={busy}>
          {busy ? '기다리는 중…' : '보내기'}
        </Button>
      </form>
    </Card>
  )
}
