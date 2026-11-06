import { useEffect, useRef } from 'react'
import { generationCopy, type GenerationFlow } from '../generation'
import { toFacts } from '../hooks'
import { PLAN_FACT_KEYS } from '../types'
import { Tori } from '@/shared/ui/Tori'
import { Button } from '@/shared/ui/Button'
import { formatCurrency } from '@/shared/lib/format'

export function GenerationScreen({
  flow,
  onReload,
  onViewCurrent,
}: {
  flow: GenerationFlow
  onReload: () => Promise<unknown>
  onViewCurrent: () => Promise<unknown>
}) {
  const title = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    title.current?.focus()
  }, [])
  const copy = generationCopy[flow.phase]
  const waiting = ['requesting', 'generating', 'verifying', 'loading', 'unknown'].includes(
    flow.phase,
  )
  const facts = toFacts(flow.draft)
  const budgetMeta = flow.draft.conditionMeta.budgetTotal ?? flow.draft.conditionMeta.budget_total
  const budgetLater = flow.draft.deferredTopics.includes('budget_total')
  return (
    <section
      aria-label="초안 생성 상태"
      className="w-full max-w-[880px] self-center rounded-2xl border border-line bg-card px-5 py-8 sm:px-10 sm:py-10"
    >
      <div className="flex items-start gap-4">
        <Tori size={48} />
        <div className="min-w-0 flex-1" role="status" aria-live="polite" aria-atomic="true">
          <h2
            ref={title}
            tabIndex={-1}
            className="text-h2 break-keep [overflow-wrap:anywhere] focus:outline-none"
          >
            {copy.title}
          </h2>
          <p className="mt-2 max-w-[65ch] break-keep text-ink2 [overflow-wrap:anywhere]">
            {copy.detail}
          </p>
        </div>
        {waiting && (
          <span
            aria-hidden="true"
            className="mt-2 size-2 shrink-0 animate-pulse rounded-full bg-blue-600 motion-reduce:animate-none"
          />
        )}
      </div>
      {(flow.phase === 'load-failed' || flow.phase === 'unconfirmed') && (
        <Button className="mt-6" onClick={() => void onReload()}>
          초안 다시 불러오기
        </Button>
      )}
      {flow.phase === 'changed' && (
        <Button className="mt-6" onClick={() => void onViewCurrent()}>
          현재 계획 확인하기
        </Button>
      )}
      {flow.phase === 'unknown' && (
        <p className="mt-5 break-keep text-caption text-ink2">
          확인하는 동안 이 계획의 새 대화와 생성은 잠가 두었어요. 다른 계획은 그대로 쓸 수 있어요.
        </p>
      )}
      <div className="mt-8 border-t border-line pt-6">
        <h3 className="font-semibold">요청 기준 조건</h3>
        <dl className="mt-4 grid min-w-0 grid-cols-1 gap-x-10 gap-y-4 sm:grid-cols-2">
          {PLAN_FACT_KEYS.map((label) => {
            const fact = facts[label] ?? { status: '미정' }
            return (
              <div key={label} className="min-w-0">
                <dt className="text-caption text-mute">{label}</dt>
                <dd className="mt-1 break-keep font-medium [overflow-wrap:anywhere]">
                  {fact.value ?? (fact.status === '나중에' ? '나중에 정하기로 했어요' : '미정')}
                  {fact.status === '잠정' && (
                    <span className="ml-2 text-caption font-normal text-ink2">잠정</span>
                  )}
                </dd>
              </div>
            )
          })}
          {(flow.draft.conditions.budgetTotal !== null || budgetLater) && (
            <div className="min-w-0">
              <dt className="text-caption text-mute">총예산</dt>
              <dd className="mt-1 font-medium">
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
    </section>
  )
}
