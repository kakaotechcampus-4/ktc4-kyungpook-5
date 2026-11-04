// P1 왼쪽: 토리와 주고받는 대화.
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import type { ChatMessage, PlanProgress } from '@/features/planning/types'
import type { TurnLine } from '@/features/planning/turn'
import { isSendKey } from '@/features/planning/chatKey'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Textarea } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'
import { ReplyText } from '@/features/planning/components/ReplyText'

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
  progress?: TurnLine[]
  pendingReply?: string
  notice?: string
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className={cn('size-[14px] shrink-0 text-done', className)}
      fill="none"
    >
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
}

// 진행 중은 작은 점, 완료는 초록 체크, 기록 없음은 회색 대시, 실패는 느낌표. 모두 같은 14px 자리를 써서
// 점이 체크로 바뀔 때 줄이 흔들리지 않는다. 진행 중임은 점이 아니라 글자 디밍이 알린다(#290).
// live면 받는 중인 응답이라 체크가 제자리에서 나타난다. 저장된 대화로 바뀐 뒤에는 다시 움직이지 않는다.
function ProgressIcon({ status, live }: { status: PlanProgress['status']; live: boolean }) {
  // skipped는 진행 중 줄이 사라지는 중이라 같은 점을 유지한다.
  if (status === 'running' || status === 'skipped')
    return (
      <span aria-hidden className="mt-[2px] flex size-[14px] shrink-0 items-center justify-center">
        <span className="size-[6px] rounded-full bg-blue-400" />
      </span>
    )
  if (status === 'completed')
    return (
      <CheckIcon
        className={cn('mt-[2px]', live && 'animate-check-in motion-reduce:animate-none')}
      />
    )
  // 기록 없음(#300): 검색은 정상으로 끝났으니 실패 표시가 아니고, 찾았다는 체크도 아니다.
  if (status === 'empty')
    return (
      <svg
        aria-hidden
        viewBox="0 0 16 16"
        className={cn(
          'mt-[2px] size-[14px] shrink-0 text-mute',
          live && 'animate-check-in motion-reduce:animate-none',
        )}
        fill="none"
      >
        <circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.15" />
        <path d="M5 8h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    )
  return (
    <span aria-hidden className="w-[14px] shrink-0 text-center font-bold text-failed">
      !
    </span>
  )
}

// 토리 응답 안의 작업 줄(#290). 답변이 나오기 전에는 지금 하는 일로 또렷하게,
// 답변이 시작되면 그 답변의 근거로 한 단계 옅게 보인다. 끝난 뒤에도 답변 위에 남는다.
// live(받는 중)일 때만 새 줄이 나타나는 움직임과 진행 중 디밍을 준다. 저장된 대화의 줄은
// 같은 내용이 다시 그려지는 것이라 움직이면 깜빡임처럼 보인다.
function TurnLines({
  lines,
  settled,
  live = false,
}: {
  lines: TurnLine[]
  settled: boolean
  live?: boolean
}) {
  return (
    <ul aria-label="토리가 처리한 작업" className="flex flex-col gap-[4px] pt-[8px]">
      {lines.map((line) => (
        <li
          key={line.slot ?? line.operationId}
          className={cn(
            // 문구가 길어 두 줄이 되면 아이콘은 첫 줄 높이에 맞춘다(아이콘 쪽 mt).
            'flex items-start gap-[7px] text-[12px] leading-[18px]',
            'transition-colors duration-200 ease-out motion-reduce:transition-none',
            line.status === 'failed'
              ? 'text-failed'
              : settled || line.status === 'empty'
                ? 'text-mute'
                : 'text-ink2',
            // 결과 없이 끝난 줄(거절·같은 값)은 답변이 시작되면 조용히 사라진다. 이유는 답변이 설명한다.
            // 그 전까지는 다시 시도될 수 있어 진행 중 줄처럼 보인다(turn.ts upsertProgress).
            line.status === 'skipped' && settled
              ? 'animate-line-out overflow-hidden motion-reduce:animate-none'
              : live && 'animate-turn-in motion-reduce:animate-none',
          )}
        >
          <ProgressIcon status={line.status} live={live} />
          <span
            className={cn(
              (line.status === 'running' || (line.status === 'skipped' && !settled)) &&
                'animate-progress-dim motion-reduce:animate-none',
            )}
          >
            {line.text}
          </span>
        </li>
      ))}
    </ul>
  )
}

// 저장된 답변 위의 작업 줄. 2줄 이상이면 답변이 끝난 뒤 "처리한 작업 2개" 한 줄로 접는다.
// 답변이 가장 중요하므로 체크 줄들이 토리 옆에서 답변보다 먼저 눈에 띄지 않게 한다.
// AI 문구를 잘라 합치지 않고 개수만 적어, 문구가 바뀌어도 요약이 깨지지 않는다.
//
//   저장 직후     ✓ 참고할 기록을 찾았어요      ← 받는 중일 때와 같은 모습(바뀌는 순간 튀지 않게)
//                ✓ 행사 종류 MT · … 반영했어요
//   잠시 뒤      ✓ 처리한 작업 2개 ▾            ← 줄 높이가 부드럽게 줄며 접힘. 누르면 다시 펼침
//
// 1줄은 접어도 높이가 같아 그대로 두고, 실패가 섞이면 알려야 하므로 접지 않는다.
const FOLD_DELAY_MS = 400

function Receipt({ lines }: { lines: PlanProgress[] }) {
  // 기록 없음(empty)은 실패가 아니라 접어도 된다.
  const foldable =
    lines.length > 1 &&
    lines.every((line) => line.status === 'completed' || line.status === 'empty')
  // fresh: 막 저장돼 펼친 채 보이는 중 → folded: 접힘 → open: 사용자가 펼침
  const [state, setState] = useState<'fresh' | 'folded' | 'open'>('fresh')
  useEffect(() => {
    if (!foldable) return
    const timer = setTimeout(() => setState((s) => (s === 'fresh' ? 'folded' : s)), FOLD_DELAY_MS)
    return () => clearTimeout(timer)
  }, [foldable])
  const listId = useId()
  if (!foldable) return <TurnLines lines={lines} settled />

  const showList = state !== 'folded'
  // grid 행 높이 0fr ↔ 1fr 전환으로 실제 높이를 몰라도 부드럽게 접고 편다.
  const collapse =
    'grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none'
  return (
    <div className="flex flex-col">
      <div className={cn(collapse, state === 'fresh' ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]')}>
        <div className="min-h-0 overflow-hidden">
          <button
            type="button"
            aria-expanded={showList}
            aria-controls={listId}
            onClick={() => setState(showList ? 'folded' : 'open')}
            className="mt-[8px] flex items-center gap-[7px] rounded-[6px] text-[12px] leading-[18px] text-mute hover:text-ink2"
          >
            <CheckIcon />
            처리한 작업 {lines.length}개
            <svg
              aria-hidden
              viewBox="0 0 12 12"
              className={cn(
                'size-[11px] transition-transform duration-200 ease-out motion-reduce:transition-none',
                showList && 'rotate-180',
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
          </button>
        </div>
      </div>
      <div
        id={listId}
        inert={!showList}
        className={cn(collapse, showList ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]')}
      >
        <div className="min-h-0 overflow-hidden">
          <TurnLines lines={lines} settled />
        </div>
      </div>
    </div>
  )
}

// 보내자마자 토리 답변 자리에 뜨는 입력 중 표시. 답변 첫 조각이 오면 같은 말풍선 안에서
// 글자로 바뀐다. 움직임 줄이기 설정이면 점 세 개가 움직이지 않고 그대로 보인다.
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

// 답변과 보낸 말은 화면의 본문 크기(text-body 14px)로 쓴다. 작업 줄(12px)보다 한 단계 커서 답변이 먼저 읽힌다.
// 한글은 받침 때문에 글자가 위아래로 차 보여 줄 간격을 넉넉히(22px, 약 1.57배) 둔다.
// 줄은 낱말 단위로 바꾼다(break-keep). 기본값이면 "좋겠습|니다"처럼 낱말 가운데서 끊긴다.
// 띄어쓰기 없는 긴 글(주소 등)은 칸을 넘지 않게 그때만 글자 단위로 끊는다(break-words).
const CHAT_TEXT = 'text-body leading-[22px] break-keep break-words'
// 넓은 화면에서도 한 줄이 한글 약 42자를 넘지 않게 폭을 묶는다. 짧은 답변은 글 길이만큼만 차지한다.
const TORI_BUBBLE = cn(
  'max-w-[42em] rounded-[12px] border border-line bg-bg px-[15px] py-[12px] text-ink [text-wrap:pretty]',
  CHAT_TEXT,
)
// 토리 답변 글. 모델이 쓴 굵게·목록·빈 줄 문단을 기호 대신 모양으로 보인다(ReplyText, #304).
const REPLY_BODY = 'flex flex-col gap-[8px]'
const USER_BUBBLE = cn(
  'ml-auto max-w-[70%] rounded-[12px] bg-blue-600 px-[15px] py-[12px] font-medium whitespace-pre-wrap text-white',
  CHAT_TEXT,
)

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

  // 보낸 글은 곧바로 입력창에서 빼서 대화 쪽 말풍선으로만 보인다. 실패하면 다시 보낼 수
  // 있게 입력창에 돌려놓는다. 빠른 답변 버튼으로 보낸 것은 입력 중이던 글을 건드리지 않는다.
  const send = async (text: string, fromInput: boolean) => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    if (fromInput) setDraft('')
    if (!(await onSend(trimmed)) && fromInput) setDraft(trimmed)
  }

  // 받는 중인 토리 응답. 보낸 말이 있거나 진행 줄·답변 조각이 오면 보인다.
  // 저장된 대화로 바뀌는 순간 hooks가 셋을 함께 비워, 저장된 답변 아래에 점이 남지 않는다.
  const showTurn = busy && (!!pendingText || progress.length > 0 || !!pendingReply)

  // 빠른 답변은 마지막 토리 말풍선에만 남긴다. 지난 질문의 선택지는 이미 지나간 것이다.
  const lastToriId = [...messages].reverse().find((m) => m.from === '토리')?.id

  return (
    <Card className="flex h-[min(70vh,700px)] min-h-[380px] w-full min-w-0 flex-col lg:flex-1">
      <header className="flex items-center justify-between border-b border-line px-[24px] py-[18px]">
        <h2 className="text-h2 text-ink">토리와 계획 잡기</h2>
        <span className="text-[12px] text-mute">
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
                <div className="flex min-w-0 flex-col items-start gap-[8px]">
                  {message.receipt && <Receipt lines={message.receipt} />}
                  <div className={cn(TORI_BUBBLE, REPLY_BODY)}>
                    <ReplyText text={message.text} />
                  </div>
                </div>
              </div>
              {message.id === lastToriId && message.quickReplies && (
                <div className="flex flex-wrap gap-[8px] pl-[36px]">
                  {message.quickReplies.map((reply) => (
                    <button
                      key={reply}
                      type="button"
                      disabled={busy}
                      onClick={() => void send(reply, false)}
                      className="rounded-[9px] border border-blue-200 bg-card px-[13px] py-[8px] text-caption font-bold text-blue-700 hover:bg-blue-50"
                    >
                      {reply}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p key={message.id} className={USER_BUBBLE}>
              {message.text}
            </p>
          ),
        )}
        {busy && pendingText && <p className={cn(USER_BUBBLE, 'opacity-80')}>{pendingText}</p>}
        {/* 받는 중인 토리 응답. 저장된 응답(위)과 같은 구조라, 저장된 대화로 바뀌어도 자리가 그대로다.
            ① 보냄: 말풍선에 점 세 개 → ② 작업 줄이 말풍선 위에 붙음 → ③ 점이 답변 글자로 바뀜 */}
        {showTurn && (
          <div className="flex items-start gap-[10px] animate-turn-in [animation-delay:100ms] motion-reduce:animate-none">
            <Tori size={26} className="mt-[4px] shrink-0" />
            <div className="flex min-w-0 flex-col items-start gap-[8px]">
              {progress.length > 0 && <TurnLines lines={progress} settled={!!pendingReply} live />}
              <div className={TORI_BUBBLE}>
                {pendingReply ? (
                  <div className={cn(REPLY_BODY, 'animate-fade-in motion-reduce:animate-none')}>
                    <ReplyText text={pendingReply} partial />
                  </div>
                ) : (
                  <TypingDots />
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {busy && (
        // 화면 낭독기는 진행 줄 변화를 여기서 한 번에 듣는다. 답변 조각마다 읽지 않는다.
        // 대화 쪽에 토리 응답이 보이면 같은 뜻을 두 번 보이지 않게 화면에서는 숨긴다.
        <p role="status" className={cn('px-[24px] text-mute', !notice && showTurn && 'sr-only')}>
          {notice ||
            (pendingReply
              ? '토리가 답변을 쓰고 있어요…'
              : (progress.filter((line) => line.status !== 'skipped').at(-1)?.text ??
                '토리가 답변을 준비하고 있어요…'))}
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
          void send(draft, true)
        }}
      >
        <div className="min-w-0 flex-1">
          {/* 기다리는 동안 막지(disabled) 않고 읽기 전용으로 둔다. 막으면 포커스가 빠져
              답변이 끝난 뒤 입력창을 다시 눌러야 한다. 읽기 전용이면 커서가 그대로 남는다. */}
          <Textarea
            aria-label="계획 대화 답변"
            aria-describedby="planning-input-help"
            rows={2}
            className="min-h-[58px] max-h-[160px] resize-y"
            readOnly={busy}
            placeholder={busy ? '토리의 답변을 기다리고 있어요' : '답을 입력하세요'}
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
          <p id="planning-input-help" className="mt-1 text-[12px] text-mute">
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
