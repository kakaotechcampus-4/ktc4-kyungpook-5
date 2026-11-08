// 토리에게 말을 보내는 입력 상자. 입력칸과 보내기 버튼을 한 상자로 묶는다.
// 행사 계획 대화(PlanChat)와 대시보드 질문(ToriChat)이 같은 모양과 단축키 안내를 쓴다.
// Enter로 보낼지는 쓰는 쪽이 onKeyDown으로 정한다(IME 조합 처리 등).
import { useId, useLayoutEffect, useRef, type Ref, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

// 한 줄 높이(22px)와 입력칸 위아래 여백(7px씩).
const LINE = 22
const PAD = 14
// pill은 입력칸 위아래 여백이 10px씩이다.
const PILL_PAD = 20

interface ChatComposerProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  value: string
  inputRef?: Ref<HTMLTextAreaElement>
  // 보내기 버튼. 글이 없거나 막혔으면 sendDisabled, 답을 기다리는 동안 도는 표시는 waiting.
  sendLabel: string
  sendDisabled: boolean
  waiting?: boolean
  // inset: 카드 안 아래에 붙는 대화 입력(회색 바탕). raised: 화면의 주 입력(흰 바탕과 옅은 그림자).
  // pill: 메인 첫 화면처럼 입력 자체가 화면의 중심일 때. 양 끝이 둥글고 글자와 버튼이 한 단계 크다.
  tone?: 'inset' | 'raised' | 'pill'
  // 처음 높이와 늘어나는 한도(줄 수). 그 뒤로는 상자 안에서 스크롤한다.
  minRows?: number
  maxRows?: number
}

export function ChatComposer({
  value,
  inputRef,
  sendLabel,
  sendDisabled,
  waiting = false,
  tone = 'inset',
  minRows = 1,
  maxRows = 5,
  disabled,
  className,
  'aria-describedby': describedBy,
  ...props
}: ChatComposerProps) {
  const ownRef = useRef<HTMLTextAreaElement>(null)
  const pad = tone === 'pill' ? PILL_PAD : PAD
  const helpId = useId()
  // 글 길이만큼 늘어나고 maxRows에서 멈춘다.
  useLayoutEffect(() => {
    const input = ownRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(input.scrollHeight, LINE * maxRows + pad)}px`
  }, [value, maxRows, pad])
  const setRef = (node: HTMLTextAreaElement | null) => {
    ownRef.current = node
    if (typeof inputRef === 'function') inputRef(node)
    else if (inputRef) inputRef.current = node
  }

  return (
    <>
      {/* 상자 빈 곳을 눌러도 입력칸에 커서가 간다. 버튼과 입력칸은 각자 눌린다. */}
      <div
        onClick={(event) => {
          if (event.target === event.currentTarget) ownRef.current?.focus()
        }}
        className={cn(
          'relative flex cursor-text items-end gap-2 border',
          tone === 'pill'
            ? 'rounded-[28px] py-[8px] pr-[8px] pl-[22px]'
            : 'rounded-[14px] py-[6px] pr-[6px] pl-[15px]',
          'transition-[border-color,background-color,box-shadow] duration-150 motion-reduce:transition-none',
          tone === 'inset'
            ? 'border-soft bg-bg focus-within:border-blue-600 focus-within:bg-card'
            : 'border-soft bg-card shadow-[0_2px_10px_rgb(32_43_56/0.06)] focus-within:border-blue-600 focus-within:shadow-[0_3px_14px_rgb(74_107_174/0.14)]',
          disabled && 'cursor-not-allowed opacity-60',
          className,
        )}
      >
        <textarea
          ref={setRef}
          rows={minRows}
          value={value}
          disabled={disabled}
          aria-describedby={[helpId, describedBy].filter(Boolean).join(' ')}
          style={{ minHeight: LINE * minRows + pad, maxHeight: LINE * maxRows + pad }}
          // 16px 미만이면 iOS Safari가 입력할 때 화면을 확대한다. 넓은 화면에서는 본문 크기로 둔다.
          className={cn(
            'min-w-0 flex-1 resize-none bg-transparent text-[16px] leading-[22px] text-ink outline-none placeholder:text-mute disabled:cursor-not-allowed',
            tone === 'pill' ? 'py-[10px]' : 'py-[7px] sm:text-body',
          )}
          {...props}
        />
        <SendButton
          label={sendLabel}
          disabled={sendDisabled || !!disabled}
          waiting={waiting}
          large={tone === 'pill'}
        />
      </div>
      {/* 단축키는 보내기 버튼 말풍선으로만 보인다. 화면 낭독기는 입력칸 설명으로 듣는다. */}
      <span id={helpId} className="sr-only">
        Enter로 보내고 Shift+Enter로 줄을 바꿔요.
      </span>
    </>
  )
}

const KEY_CAP = 'rounded-[4px] bg-white/15 px-[5px] py-[1px] font-sans font-semibold'

// 글이 없으면 회색, 있으면 파랑, 답을 기다리면 도는 표시.
// 마우스를 올리거나 키보드로 오면 단축키 말풍선이 뜬다. 막힌 상태에서도 말풍선은 볼 수 있다.
function SendButton({
  label,
  disabled,
  waiting,
  large = false,
}: {
  label: string
  disabled: boolean
  waiting: boolean
  large?: boolean
}) {
  return (
    // 말풍선은 상자 위에 뜬다(상자가 기준). 버튼 위에 띄우면 두 줄 상자에서 입력한 글을 가린다.
    <div className="group/send shrink-0">
      <button
        type="submit"
        aria-label={label}
        aria-busy={waiting || undefined}
        disabled={disabled || waiting}
        className={cn(
          'flex items-center justify-center rounded-full',
          large ? 'size-[42px]' : 'size-[36px]',
          'transition-colors duration-150 motion-reduce:transition-none',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600',
          waiting
            ? 'cursor-wait bg-blue-600 text-white'
            : disabled
              ? 'cursor-not-allowed bg-track text-mute'
              : 'bg-blue-600 text-white hover:bg-blue-700',
        )}
      >
        {waiting ? (
          <svg
            aria-hidden
            viewBox="0 0 16 16"
            className="size-[16px] animate-spin motion-reduce:animate-none"
            fill="none"
          >
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
            <path
              d="M8 2a6 6 0 0 1 6 6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        ) : (
          <svg aria-hidden viewBox="0 0 16 16" className="size-[16px]" fill="none">
            <path
              d="M8 13V3.5M3.8 7.6 8 3.4l4.2 4.2"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
      <span
        aria-hidden
        className={cn(
          'pointer-events-none absolute right-0 bottom-full z-10 mb-[8px] flex items-center gap-[4px] rounded-[8px] bg-ink px-[10px] py-[6px] text-[12px] leading-[16px] whitespace-nowrap text-white',
          'translate-y-[2px] opacity-0 transition-[opacity,translate] duration-150 ease-out motion-reduce:transition-none',
          'group-hover/send:translate-y-0 group-hover/send:opacity-100 group-hover/send:delay-300',
          'group-has-[:focus-visible]/send:translate-y-0 group-has-[:focus-visible]/send:opacity-100',
        )}
      >
        <kbd className={KEY_CAP}>Enter</kbd>보내기
        <span className="px-[2px] text-white/50">·</span>
        <kbd className={KEY_CAP}>Shift</kbd>+<kbd className={KEY_CAP}>Enter</kbd>줄바꿈
      </span>
    </div>
  )
}
