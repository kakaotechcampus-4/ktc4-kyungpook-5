// 메인 토리 데스크. 첫 화면은 브리핑, 질문을 보내면 브리핑이 위로 접히고 대화가 이어진다.
// 토리 답은 한 줄 문장과 카드로 나온다. 대화는 서버에 남기지 않아 새로고침하면 사라진다.
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { isSendKey } from '@/features/planning/chatKey'
import { BriefingPanel, Chevron } from '@/features/dashboard/components/BriefingPanel'
import { RecordReply } from '@/features/dashboard/components/RecordReply'
import { ToriCardView } from '@/features/dashboard/components/ToriCards'
import type { BriefingState, Navigation, ToriDeskReply } from '@/features/dashboard/desk'
import { useDeskPath } from '@/features/dashboard/desk'
import type { components } from '@/shared/api/schema'
import { ApiError } from '@/shared/api/types'
import { cn } from '@/shared/lib/cn'
import { ChatComposer } from '@/shared/ui/ChatComposer'
import { Tori } from '@/shared/ui/Tori'

type ClarificationContext = components['schemas']['ToriClarificationContext']
type Turn = Question & { reply: ToriDeskReply }
// 자료 찾기에서 토리가 되물은 뒤의 질문은 되물은 맥락을 함께 보낸다.
type Question = { id: string; message: string; clarification: Pending | null }
type Pending = ClarificationContext & { turnId: string }

export type Respond = (
  message: string,
  clarification: ClarificationContext | null,
) => Promise<ToriDeskReply>

// 토리가 하지 않는 일을 할 수 있는 화면
const NAVIGATION: Record<Navigation, string> = {
  '/planning': '계획 화면으로 가기',
  '/meetings': '회의 화면으로 가기',
  '/records': '자료 화면으로 가기',
  '/accounting': '회계 화면으로 가기',
}

// 지금 주고받는 질문 칸의 최소 높이. 답이 오기 전부터 답 자리를 잡아 두어,
// 보내는 순간 한 번만 스크롤하고 답이 와도 화면이 움직이지 않는다(아래 입력 상자 높이만큼 뺀다).
const CURRENT_TURN = 'min-h-[calc(100dvh-160px)]'
// 브리핑 접힘 시간(아래 grid 전환 duration-300과 같다)
const FOLD_MS = 300
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

// 질문 한 번에 보낼 수 있는 글자 수(서버 한도와 같다).
const MAX_QUESTION = 1000

// 말풍선은 행사 계획 대화와 같은 크기·색을 쓴다.
const CHAT_TEXT = 'text-body leading-[22px] break-keep break-words'
const USER_BUBBLE = cn(
  'ml-auto w-fit max-w-[70%] rounded-[12px] bg-blue-600 px-[15px] py-[12px] font-medium whitespace-pre-wrap text-white',
  CHAT_TEXT,
)
const TORI_BUBBLE = cn(
  'w-fit max-w-[42em] rounded-[12px] border border-line bg-bg px-[15px] py-[12px] text-ink [text-wrap:pretty]',
  CHAT_TEXT,
)
const SUGGESTION =
  'rounded-full border border-blue-200 bg-card px-[15px] py-[8px] text-caption font-bold text-blue-700 transition-colors hover:bg-blue-50 disabled:opacity-50'

function TypingDots() {
  return (
    <span aria-hidden className="flex h-[22px] items-center gap-[4px] px-[2px]">
      {['0ms', '150ms', '300ms'].map((delay) => (
        <span
          key={delay}
          style={{ animationDelay: delay }}
          className="size-[5px] rounded-full bg-mute animate-typing-dot motion-reduce:animate-none"
        />
      ))}
    </span>
  )
}

function ToriTurn({
  reply,
  showSuggestions,
  answering,
  busy,
  onSuggest,
}: {
  reply: ToriDeskReply
  showSuggestions: boolean
  // 이 답이 되물은 질문이고 아직 답하지 않았는지. 선택지를 누를 수 있다.
  answering: boolean
  busy: boolean
  onSuggest: (text: string) => void
}) {
  const path = useDeskPath()
  const options = reply.clarification?.options ?? []
  // 되물을 때는 선택지가 이어 물을 말이다. 「전체 요약」은 범위를 좁히지 않고 원래 질문 그대로 답을 받는다.
  const suggestions = reply.clarification
    ? [...options, ...(options.some((option) => option.replace(/\s/g, '') === '전체요약') ? [] : ['전체 요약'])]
    : (reply.suggestions ?? [])
  const clickable = reply.clarification ? answering : showSuggestions
  return (
    <div className="flex items-start gap-[10px]">
      <Tori size={26} className="mt-[4px]" />
      <div className="flex min-w-0 flex-1 animate-turn-in flex-col items-start gap-[10px] motion-reduce:animate-none">
        {reply.records ? (
          <div className={cn(TORI_BUBBLE, 'w-full')}>
            <RecordReply result={reply.records} />
          </div>
        ) : (
          <p className={TORI_BUBBLE}>{reply.reply}</p>
        )}
        {reply.card && (
          <div className="w-full max-w-[640px] animate-turn-in motion-reduce:animate-none">
            <ToriCardView card={reply.card} />
          </div>
        )}
        {reply.navigation && (
          <Link
            to={path(reply.navigation)}
            className="flex items-center gap-[6px] rounded-full border border-line bg-card py-[8px] pr-[13px] pl-[15px] text-caption font-bold text-ink transition-colors hover:border-soft hover:bg-bg"
          >
            {NAVIGATION[reply.navigation]}
            <Chevron className="text-mute" />
          </Link>
        )}
        {clickable && suggestions.length > 0 && (
          <div className="flex flex-wrap gap-[8px] pt-[2px]">
            {suggestions.map((text) => (
              <button
                key={text}
                type="button"
                disabled={busy}
                onClick={() => onSuggest(text)}
                className={SUGGESTION}
              >
                {text}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function ToriDesk({
  briefing,
  starters,
  respond,
}: {
  briefing: BriefingState
  starters: string[]
  respond: Respond
}) {
  const [draft, setDraft] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [active, setActive] = useState<Question | null>(null)
  const [waiting, setWaiting] = useState(0)
  const [error, setError] = useState('')
  const [briefOpen, setBriefOpen] = useState(true)
  // 토리가 되물어 답을 기다리는 중. 다음 질문에 맥락을 붙인다.
  const [pending, setPending] = useState<Pending | null>(null)
  const pendingRef = useRef<Pending | null>(null)
  const queue = useRef<Question[]>([])
  const processing = useRef(false)
  const current = useRef<HTMLDivElement>(null)
  // 보낼 때 브리핑이 펼쳐져 있었는지. 접히는 동안에는 질문 칸 자리가 계속 바뀐다.
  const folding = useRef(false)
  const started = turns.length > 0 || busy

  // 질문을 보내면 그 질문이 화면 위쪽에 오도록 바로 부드럽게 옮긴다. 답이 오면 같은 칸이 채워질 뿐이라
  // 다시 움직이지 않는다. 브리핑이 접히는 중이면 다 접힌 뒤의 자리로 간다.
  useEffect(() => {
    if (!active) return
    const behavior = reducedMotion() ? 'auto' : 'smooth'
    // 스크롤 함수의 반환값(최신 브라우저는 Promise)을 effect 정리 함수로 돌려주지 않는다.
    const move = () => {
      current.current?.scrollIntoView({ block: 'start', behavior })
    }
    if (!folding.current) {
      move()
      return
    }
    folding.current = false
    // 첫 질문: 브리핑이 접히면 대화가 맨 위에서 시작한다. 접힘과 함께 위로 올라간다.
    if (turns.length === 0) {
      window.scrollTo({ top: 0, behavior })
      return
    }
    const timer = window.setTimeout(move, FOLD_MS)
    return () => window.clearTimeout(timer)
    // 질문이 바뀔 때만 옮긴다. 답이 와서 turns가 늘 때는 움직이지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id])

  const processQueue = async () => {
    if (processing.current) return
    processing.current = true
    setBusy(true)
    try {
      while (queue.current.length > 0) {
        const question = queue.current.shift()!
        setWaiting(queue.current.length)
        setActive(question)
        setError('')
        try {
          const asked = question.clarification
          const reply = await respond(
            question.message,
            asked
              ? {
                  originalQuestion: asked.originalQuestion,
                  question: asked.question,
                  options: asked.options,
                }
              : null,
          )
          setTurns((items) => [...items, { ...question, reply }])
          // 되물은 질문에 답했는데 자료 답을 만들지 못했으면, 같은 맥락으로 다시 답할 수 있게 둔다.
          if (question.clarification && reply.records?.recordAnswer?.status === 'failed') continue
          const next = reply.clarification
            ? {
                turnId: question.id,
                originalQuestion: reply.clarification.originalQuestion,
                question: reply.clarification.question,
                options: reply.clarification.options ?? [],
              }
            : null
          pendingRef.current = next
          setPending(next)
        } catch (cause) {
          setError(
            cause instanceof ApiError && cause.code === 'AI_MISCONFIGURED'
              ? '토리 대화 설정을 확인하고 있어요. 잠시 후 다시 보내 주세요.'
              : '답을 가져오지 못했어요. 연결을 확인하고 다시 보내 주세요.',
          )
        }
      }
    } finally {
      processing.current = false
      setBusy(false)
      setActive(null)
      setWaiting(0)
    }
  }

  const send = (text: string) => {
    const message = text.trim()
    if (!message) return
    if (briefOpen) folding.current = true
    setBriefOpen(false)
    queue.current.push({ id: crypto.randomUUID(), message, clarification: pendingRef.current })
    setWaiting(queue.current.length)
    setDraft('')
    void processQueue()
  }

  const inputRef = useRef<HTMLTextAreaElement>(null)
  // 첫 질문을 보내면 입력 상자가 아래로 옮겨 간다. 이어서 쓸 수 있게 커서도 따라간다.
  useEffect(() => {
    if (started) inputRef.current?.focus({ preventScroll: true })
  }, [started])

  // 입력 상자. 대화 전에는 토리 문장 바로 아래(위쪽)에, 대화가 시작되면 화면 아래에 붙는다.
  const composer = (docked: boolean) => (
    <div className="flex flex-col gap-[10px]">
      {error && (
        <p
          role="alert"
          className="rounded-[10px] border border-failed-line bg-failed-bg px-3 py-2 text-caption text-failed"
        >
          {error}
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault()
          send(draft)
        }}
      >
        <ChatComposer
          inputRef={inputRef}
          tone="pill"
          minRows={1}
          maxRows={6}
          aria-label="토리에게 질문"
          maxLength={MAX_QUESTION}
          placeholder={docked ? '이어서 물어보세요' : '토리에게 무엇이든 물어보세요'}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (
              !isSendKey({
                key: event.key,
                shiftKey: event.shiftKey,
                altKey: event.altKey,
                ctrlKey: event.ctrlKey,
                metaKey: event.metaKey,
                isComposing: event.nativeEvent.isComposing,
                keyCode: event.keyCode,
              })
            )
              return
            event.preventDefault()
            if (!event.repeat) event.currentTarget.form?.requestSubmit()
          }}
          // 답을 기다리는 동안에도 다음 질문을 받아 차례로 처리한다.
          sendLabel={busy ? '질문 추가' : '보내기'}
          sendDisabled={!draft.trim()}
        />
      </form>
      {!docked && starters.length > 0 && (
        <div className="flex flex-wrap gap-[8px]">
          {starters.map((text) => (
            <button key={text} type="button" onClick={() => send(text)} className={SUGGESTION}>
              {text}
            </button>
          ))}
        </div>
      )}
      {docked && (
        <div className="flex items-center justify-between gap-3 px-[2px] text-label text-mute">
          <p>
            {waiting > 0
              ? `질문 ${waiting}개가 순서대로 처리돼요.`
              : pending
                ? '토리의 질문에 이어서 답하고 있어요.'
                : '대화는 새로고침하면 사라져요.'}
          </p>
          {pending && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                pendingRef.current = null
                setPending(null)
              }}
              className="shrink-0 font-semibold text-blue-700 underline-offset-4 hover:underline disabled:opacity-50"
            >
              새 질문하기
            </button>
          )}
        </div>
      )}
    </div>
  )

  // 답을 받은 질문과, 지금 답을 기다리는 질문
  const blocks: Array<Question & { reply?: ToriDeskReply }> = [
    ...turns,
    ...(busy && active ? [active] : []),
  ]

  return (
    <div className="mx-auto flex w-full max-w-[880px] flex-col">
      {started && (
        <button
          type="button"
          aria-expanded={briefOpen}
          aria-controls="tori-briefing"
          onClick={() => setBriefOpen((open) => !open)}
          className="mb-[22px] flex items-center gap-[10px] rounded-full border border-line bg-bg py-[10px] pr-[18px] pl-[14px] text-left text-caption text-ink2 transition-colors hover:border-soft"
        >
          <Tori size={22} />
          <span className="min-w-0 flex-1 truncate">
            {briefing.status === 'ready' ? (
              <>
                <span className="font-bold text-ink">확인할 일 {briefing.data.items.length}개</span>
                {' | '}진행 중인 행사{' '}
                {briefing.data.events.filter((event) => event.status === 'ON_GOING').length}개
              </>
            ) : (
              <span className="font-bold text-ink">오늘 브리핑</span>
            )}
          </span>
          <span className="flex shrink-0 items-center gap-[4px] font-semibold text-blue-700">
            {briefOpen ? '브리핑 접기' : '브리핑 펼치기'}
            <svg
              aria-hidden
              viewBox="0 0 12 12"
              className={cn(
                'size-[11px] transition-transform duration-200 ease-out motion-reduce:transition-none',
                briefOpen && 'rotate-180',
              )}
              fill="none"
            >
              <path
                d="m3 4.5 3 3 3-3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </button>
      )}

      {/* 접고 펼 때 실제 높이를 몰라도 부드럽게 움직이도록 grid 행 높이를 바꾼다. */}
      <div
        id="tori-briefing"
        inert={!briefOpen}
        className={cn(
          'grid transition-[grid-template-rows,opacity] duration-300 ease-out motion-reduce:transition-none',
          briefOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <div className={cn(started ? 'pb-[30px]' : 'pb-[8px]')}>
            <BriefingPanel briefing={briefing} onAsk={send}>
              {/* 토리 문장에 바로 답하는 자리. 글 시작을 토리 문장과 맞춰 대화처럼 읽히게 한다. */}
              {!started && composer(false)}
            </BriefingPanel>
          </div>
        </div>
      </div>

      {started && (
        <div aria-label="토리 대화 내용" aria-live="polite" className="flex flex-col gap-[22px]">
          {/* 질문 칸은 보낸 순간부터 같은 키로 남는다. 답이 오면 입력 중 표시 자리만 답으로 바뀐다. */}
          {blocks.map((item, index) => {
            const last = index === blocks.length - 1
            const reply = item.reply
            return (
              <div
                key={item.id}
                ref={last ? current : undefined}
                className={cn('flex scroll-mt-[24px] flex-col gap-[14px]', last && CURRENT_TURN)}
              >
                <p className={cn(USER_BUBBLE, 'animate-turn-in motion-reduce:animate-none')}>
                  {item.message}
                </p>
                {reply ? (
                  <ToriTurn
                    reply={reply}
                    busy={busy}
                    showSuggestions={last && !busy}
                    answering={!busy && pending?.turnId === item.id}
                    onSuggest={send}
                  />
                ) : (
                  <div className="flex animate-fade-in items-start gap-[10px] motion-reduce:animate-none">
                    <Tori size={26} thinking className="mt-[4px]" />
                    <div className={TORI_BUBBLE}>
                      <TypingDots />
                    </div>
                    <span role="status" className="sr-only">
                      토리가 답을 준비하고 있어요
                    </span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 대화 중에는 입력 상자가 화면 아래에 붙는다. 위로 지나가는 내용이 상자 뒤로 흐리게 사라진다. */}
      {started && (
        <div
          className="sticky bottom-0 z-10 mt-[22px] pt-[18px] pb-[16px]"
          style={{ background: 'linear-gradient(to bottom, rgb(255 255 255 / 0), #fff 22px)' }}
        >
          {composer(true)}
        </div>
      )}
    </div>
  )
}
