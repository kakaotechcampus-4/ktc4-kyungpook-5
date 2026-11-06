// 초안 생성 화면. P1(행사 조건)과 P2(계획 검토) 사이에 끼어든다.
//
// 「이 조건으로 초안 만들기」 → 생성 화면
//   ✓ 조건 확인
//   ● 초안 작성 12초      ← generation_started부터 1초씩 센다
//   ○ 저장 확인
//   ○ 계획 불러오기
// → 모두 ✓ → "초안이 준비됐어요" → DONE_HOLD_MS 뒤 계획 검토로(「바로 보기」로 먼저 갈 수 있다)
// → 실패면 멈춘 줄에 ! → 이유와 「대화로 돌아가기」
//
// 진행 줄은 실제로 지난 구간만 체크한다(generationRows). 남은 시간이나 퍼센트는 모르므로 보이지 않는다.
import { useEffect, useId, useRef, useState } from 'react'
import {
  GENERATION_ROWS,
  generationCopy,
  generationRows,
  regenerationCopy,
  type GenerationFlow,
  type GenerationPhase,
  type GenerationRowState,
} from '../generation'
import { toFacts } from '../hooks'
import { PLAN_FACT_KEYS } from '../types'
import { Tori } from '@/shared/ui/Tori'
import { Button } from '@/shared/ui/Button'
import { cn } from '@/shared/lib/cn'
import { formatCurrency } from '@/shared/lib/format'

// 완료를 보여 주는 시간. 제목과 한 줄 설명을 읽을 수 있을 만큼 둔다.
// 움직임 줄이기 설정이어도 같은 시간 머문다. 바닥 막대만 보이지 않는다.
export const DONE_HOLD_MS = 1800

export type GenerationEnding =
  | { kind: 'done'; count: number }
  // cause: clarify 조건이 더 필요함 | failed 모델이 초안을 완성하지 못함 | error 요청 처리 오류(저장 충돌 등)
  | {
      kind: 'failed'
      cause: 'clarify' | 'failed' | 'error'
      reason: string
      stoppedAt: GenerationPhase
    }

const FAILED_TITLE = {
  clarify: '초안을 만들기 전에 확인할 내용이 있어요',
  failed: '초안을 완성하지 못했어요',
  error: '초안 생성을 마치지 못했어요',
} as const

const WAITING: GenerationPhase[] = ['requesting', 'generating', 'verifying', 'loading', 'unknown']

const STATE_TEXT: Record<GenerationRowState, string> = {
  done: '끝남',
  active: '진행 중',
  pending: '기다리는 중',
  failed: '멈춤',
  unknown: '확인하지 못함',
}

// 모두 같은 18px 자리를 써서 줄 상태가 바뀌어도 글자가 흔들리지 않는다.
function RowMark({ state }: { state: GenerationRowState }) {
  if (state === 'done')
    return (
      <svg
        aria-hidden
        viewBox="0 0 18 18"
        className="relative size-[18px] shrink-0 animate-check-in text-done motion-reduce:animate-none"
        fill="none"
      >
        <circle cx="9" cy="9" r="9" className="fill-done-bg" />
        <path
          d="M5.2 9.3 7.9 12l4.9-5.6"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  if (state === 'active')
    return (
      <span
        aria-hidden
        className="relative grid size-[18px] shrink-0 place-items-center rounded-full border-[1.5px] border-blue-400 bg-card"
      >
        <span className="size-[6px] animate-progress-dim rounded-full bg-blue-600 motion-reduce:animate-none" />
      </span>
    )
  if (state === 'failed')
    return (
      <svg aria-hidden viewBox="0 0 18 18" className="relative size-[18px] shrink-0 text-failed">
        <circle cx="9" cy="9" r="9" className="fill-failed-bg" />
        <path d="M9 4.8v5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
        <circle cx="9" cy="12.9" r="1.1" fill="currentColor" />
      </svg>
    )
  if (state === 'unknown')
    return (
      <svg aria-hidden viewBox="0 0 18 18" className="relative size-[18px] shrink-0 text-mute">
        <circle cx="9" cy="9" r="9" className="fill-track" />
        <path d="M5.8 9h6.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    )
  return <span aria-hidden className="relative block size-[18px] shrink-0 rounded-full bg-track" />
}

export function GenerationScreen({
  flow,
  ending = null,
  regenerate = false,
  hasPrevious = false,
  onReload,
  onViewCurrent,
  onBackToChat,
  onOpenReview,
}: {
  flow: GenerationFlow
  ending?: GenerationEnding | null
  // 지금 초안이 있는데 다시 만드는 중인가
  regenerate?: boolean
  // 실패했을 때 지난 초안이 남아 있는가
  hasPrevious?: boolean
  onReload: () => Promise<unknown>
  onViewCurrent: () => Promise<unknown>
  onBackToChat: () => void
  onOpenReview?: () => void
}) {
  const title = useRef<HTMLHeadingElement>(null)
  const progressId = useId()
  useEffect(() => {
    title.current?.focus()
  }, [])
  const phase = ending?.kind ?? flow.phase
  // 실패하면 키보드 초점을 제목으로 옮긴다. 바로 아래에 「대화로 돌아가기」가 있다.
  useEffect(() => {
    if (phase === 'failed') title.current?.focus()
  }, [phase])

  // 초안 작성 구간에서만 1초씩 센다. 다음 줄로 넘어가면 걸린 시간을 그대로 남긴다.
  // 새로고침 뒤 결과를 확인하는 화면은 시작을 보지 못했으므로 시간을 보이지 않는다.
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (phase !== 'generating') return
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [phase])

  // 완료를 잠시 보인 뒤 계획 검토로 넘어간다. 화면이 다시 그려져도 시간이 처음부터 다시 돌지 않게 한다.
  const openReview = useRef(onOpenReview)
  useEffect(() => {
    openReview.current = onOpenReview
  }, [onOpenReview])
  useEffect(() => {
    if (phase !== 'done') return
    const timer = setTimeout(() => openReview.current?.(), DONE_HOLD_MS)
    return () => clearTimeout(timer)
  }, [phase])

  const copy =
    ending?.kind === 'done'
      ? {
          title: regenerate ? '새 초안이 준비됐어요' : '초안이 준비됐어요',
          detail: regenerate
            ? `지금 초안을 새 초안으로 바꿨어요. 준비 단계는 ${ending.count}개예요.`
            : `준비 단계 ${ending.count}개를 만들었어요.`,
        }
      : ending?.kind === 'failed'
        ? {
            title: FAILED_TITLE[ending.cause],
            detail: ending.reason || '행사 조건을 확인해 주세요.',
          }
        : (regenerate && regenerationCopy[flow.phase]) || generationCopy[flow.phase]
  const waiting = !ending && WAITING.includes(flow.phase)
  const rows = generationRows(phase, ending?.kind === 'failed' ? ending.stoppedAt : undefined)
  const facts = toFacts(flow.draft)
  const budgetMeta = flow.draft.conditionMeta.budgetTotal ?? flow.draft.conditionMeta.budget_total
  const budgetLater = flow.draft.deferredTopics.includes('budget_total')
  return (
    <section
      aria-label="초안 생성 상태"
      // P1의 조건 카드와 같은 이름. 화면이 바뀔 때 조건 카드가 이 자리로 옮겨 오며 커진다.
      className="relative w-full max-w-[880px] self-center overflow-hidden rounded-2xl border border-line bg-card px-5 py-8 [view-transition-name:plan-generation] sm:px-10 sm:py-10"
    >
      <div className="flex items-start gap-4">
        <Tori size={48} />
        <div className="min-w-0 flex-1" role="status" aria-live="polite" aria-atomic="true">
          <h2
            ref={title}
            tabIndex={-1}
            className="text-h2 break-keep [overflow-wrap:anywhere] focus:outline-none"
          >
            {/* 제목이 바뀔 때만 살짝 올라온다. 제목 요소는 그대로 두어 초점을 잃지 않는다. */}
            <span key={copy.title} className="block animate-turn-in motion-reduce:animate-none">
              {copy.title}
            </span>
          </h2>
          <p className="mt-2 max-w-[65ch] break-keep text-ink2 [overflow-wrap:anywhere]">
            {copy.detail}
          </p>
          {ending?.kind === 'failed' && hasPrevious && (
            <p className="mt-1 break-keep text-caption text-ink2">지금 초안은 그대로예요.</p>
          )}
        </div>
      </div>

      {/* 넓은 화면에서는 진행 상황과 요청 기준 조건을 나란히 둔다. 한 화면 안에 들어와
          무엇을 하고 있는지와 무엇을 기준으로 하는지를 함께 볼 수 있다. */}
      <div className="mt-8 grid min-w-0 grid-cols-1 gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] md:gap-10">
        <div className="min-w-0">
          <h3 id={progressId} className="font-semibold">
            진행 상황
          </h3>
          <ol aria-labelledby={progressId} className="mt-3 flex flex-col">
            {GENERATION_ROWS.map((label, index) => {
              const state = rows[index]
              const last = index === GENERATION_ROWS.length - 1
              return (
                <li
                  key={label}
                  aria-current={state === 'active' ? 'step' : undefined}
                  className="relative flex items-center gap-3 py-[7px]"
                >
                  {/* 줄 사이 선. 지나온 구간만 초록으로 잇는다. */}
                  {!last && (
                    <span
                      aria-hidden
                      className={cn(
                        'absolute top-[25px] bottom-[-7px] left-[8.5px] w-px transition-colors duration-300 motion-reduce:transition-none',
                        state === 'done' ? 'bg-done/35' : 'bg-line',
                      )}
                    />
                  )}
                  <RowMark key={state} state={state} />
                  <span
                    className={cn(
                      'text-body',
                      state === 'active' &&
                        'animate-progress-dim font-semibold text-ink motion-reduce:animate-none',
                      state === 'done' && 'text-ink',
                      state === 'failed' && 'font-semibold text-failed',
                      (state === 'pending' || state === 'unknown') && 'text-mute',
                    )}
                  >
                    {label}
                  </span>
                  <span className="sr-only">{STATE_TEXT[state]}</span>
                  {index === 1 && seconds > 0 && (
                    <span className="text-caption text-mute tabular-nums" aria-hidden>
                      {seconds}초
                    </span>
                  )}
                </li>
              )
            })}
          </ol>

          {/* 화면만 바꾼다. 요청은 그대로 이어지므로 「취소」라고 쓰지 않는다(#327). */}
          {waiting && (
            <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2">
              <Button variant="secondary" onClick={onBackToChat}>
                대화로 돌아가기
              </Button>
              <p className="break-keep text-caption text-ink2">생성은 계속돼요.</p>
            </div>
          )}
          {ending?.kind === 'done' && (
            <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2">
              <Button onClick={onOpenReview}>바로 보기</Button>
              <p className="break-keep text-caption text-ink2">곧 계획 검토로 넘어가요.</p>
            </div>
          )}
          {ending?.kind === 'failed' && (
            <Button className="mt-6" onClick={onBackToChat}>
              대화로 돌아가기
            </Button>
          )}
          {!ending && (flow.phase === 'load-failed' || flow.phase === 'unconfirmed') && (
            <Button className="mt-6" onClick={() => void onReload()}>
              초안 다시 불러오기
            </Button>
          )}
          {!ending && flow.phase === 'changed' && (
            <Button className="mt-6" onClick={() => void onViewCurrent()}>
              현재 계획 확인하기
            </Button>
          )}
          {!ending && flow.phase === 'unknown' && (
            <p className="mt-5 break-keep text-caption text-ink2">
              확인하는 동안 이 계획의 새 대화와 생성은 잠가 두었어요. 다른 계획은 그대로 쓸 수
              있어요.
            </p>
          )}
        </div>

        {/* P1 오른쪽 조건 카드와 같은 모양(이름 왼쪽, 값 오른쪽). 그 카드가 이 화면으로 커져 온다. */}
        <div className="min-w-0 border-t border-line pt-6 md:border-t-0 md:border-l md:pt-0 md:pl-10">
          <h3 className="font-semibold">요청 기준 조건</h3>
          <dl className="mt-3 flex flex-col">
            {PLAN_FACT_KEYS.map((label) => {
              const fact = facts[label] ?? { status: '미정' }
              return (
                <div
                  key={label}
                  className="flex min-w-0 items-baseline justify-between gap-4 border-b border-line/70 py-[9px] last:border-b-0"
                >
                  <dt className="shrink-0 text-caption text-ink2">{label}</dt>
                  <dd className="min-w-0 break-keep text-right font-medium [overflow-wrap:anywhere]">
                    {fact.value ?? (fact.status === '나중에' ? '나중에 정하기로 했어요' : '미정')}
                    {fact.status === '잠정' && (
                      <span className="ml-2 text-caption font-normal text-ink2">잠정</span>
                    )}
                  </dd>
                </div>
              )
            })}
            {(flow.draft.conditions.budgetTotal !== null || budgetLater) && (
              <div className="flex min-w-0 items-baseline justify-between gap-4 py-[9px]">
                <dt className="shrink-0 text-caption text-ink2">총예산</dt>
                <dd className="min-w-0 text-right font-medium">
                  {flow.draft.conditions.budgetTotal === null
                    ? '나중에 정하기로 했어요'
                    : formatCurrency(flow.draft.conditions.budgetTotal)}
                  {budgetMeta?.status === 'tentative' && (
                    <span className="ml-2 text-caption font-normal text-ink2">잠정</span>
                  )}
                </dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      {/* 계획 검토로 넘어가기까지 남은 시간. 카드 위 가장자리에서 줄어든다. 긴 화면에서도 보이게 위에 둔다.
          움직임 줄이기면 숨긴다. 넘어가는 시간은 같다. */}
      {ending?.kind === 'done' && (
        <span
          aria-hidden
          style={{ animationDuration: `${DONE_HOLD_MS}ms` }}
          className="absolute inset-x-0 top-0 h-[3px] origin-left animate-hold-bar bg-blue-600 motion-reduce:hidden"
        />
      )}
    </section>
  )
}
