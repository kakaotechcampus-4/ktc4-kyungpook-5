// P1 오른쪽: 대화에서 정해진 것이 쌓이는 자리. 여섯 항목으로 고정이라 화면이 흔들리지 않는다.
import { useEffect, useId, useMemo, useState, type ReactNode } from 'react'
import { flashLeft, type FactFlash } from '@/features/planning/factFlash'
import type { PlanFactKey, PlanFactStatus, PlanFacts as Facts } from '@/features/planning/types'
import { PLAN_FACT_KEYS } from '@/features/planning/types'
import { cn } from '@/shared/lib/cn'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

function Mark({ status, required }: { status: PlanFactStatus; required?: boolean }) {
  if (status === '확정') {
    return (
      <span
        aria-hidden
        className="flex size-[18px] shrink-0 items-center justify-center rounded-full bg-blue-600 text-white"
      >
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
          <path
            d="m2.5 6 2.2 2.2L9.5 3.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    )
  }
  if (status === '잠정') {
    return (
      <span
        aria-hidden
        className="flex size-[18px] shrink-0 items-center justify-center rounded-full border-[1.5px] border-blue-300 bg-card text-blue-600"
      >
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
          <path d="M3 6h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </span>
    )
  }
  if (required)
    return (
      <span
        aria-hidden
        className="block size-[18px] shrink-0 rounded-full border-[1.5px] border-pending-line bg-pending-bg"
      />
    )
  return <span aria-hidden className="block size-[18px] shrink-0 rounded-full bg-track" />
}

interface PlanFactsProps {
  facts: Facts
  // 호출부가 서버 판정과 요청 상태에 맞는 생성 안내·행동을 넣는다.
  children?: ReactNode
  // 조건 완료 또는 저장 결과 보정으로 바뀐 칸(#302). 그 칸만 옅은 파란 배경이 잠시 켜졌다 사라진다.
  flash?: FactFlash | null
  // 초안을 만들려면 먼저 정해야 하는 칸(서버 생성 판정의 이유). 값이 없으면 「필요해요」로 보인다.
  needed?: readonly PlanFactKey[]
}

// 강조가 켜져 있는 동안의 값. 남은 시간이 지나면 비워 다시 그릴 때 지난 강조가 켜지지 않게 한다.
function useActiveFlash(flash: FactFlash | null | undefined): FactFlash | null {
  const [expired, setExpired] = useState<FactFlash | null>(null)
  useEffect(() => {
    const left = flashLeft(flash, Date.now())
    if (!left) return
    const timer = setTimeout(() => setExpired(flash ?? null), left)
    return () => clearTimeout(timer)
  }, [flash])
  // effect에서 강조를 켜면 값·체크보다 한 번 늦게 그려진다. 이번 렌더에서 바로 판단한다.
  return flash !== expired && flashLeft(flash, Date.now()) ? (flash ?? null) : null
}

export function PlanFacts({ facts, children, flash, needed }: PlanFactsProps) {
  const titleId = useId()
  const active = useActiveFlash(flash)
  // 주소 이동으로 다시 그려져도 이미 지난 시간만큼 색이 사라진 지점에서 이어 간다.
  const flashDelay = useMemo(() => (flash ? Math.min(0, flash.at - Date.now()) : 0), [flash])

  return (
    <Card
      role="region"
      aria-labelledby={titleId}
      className="flex w-full min-w-0 flex-col gap-4 px-[22px] pt-5 pb-[22px]"
    >
      <h2 id={titleId} className="text-h2 text-ink">
        이번 행사 조건
      </h2>

      {/* 줄마다 위아래 5px을 둬 강조 배경이 글자에 붙지 않게 하고, 그만큼 줄 간격과 바깥 여백을 줄여
            강조가 없을 때의 간격은 예전(16px)과 같다. */}
      <dl className="-my-[5px] flex flex-col gap-[6px]">
        {PLAN_FACT_KEYS.map((key) => {
          const fact = facts[key]
          const status = fact?.status ?? '미정'
          const settled = status === '확정' || status === '잠정'
          const flashing = active?.keys.includes(key)
          const required = !settled && status !== '나중에' && !fact?.value && needed?.includes(key)
          return (
            <div
              key={key}
              className="relative grid grid-cols-[94px_minmax(0,1fr)] items-start gap-x-3 gap-y-1 py-[5px]"
            >
              <dt className="flex items-center gap-[9px] text-label text-ink2">
                {/* 강조는 원래 행 전체를 덮고, 텍스트와 상태 표시는 그 위에 남긴다. */}
                {flashing && (
                  <span
                    key={active!.at}
                    aria-hidden
                    style={{ animationDelay: `${flashDelay}ms` }}
                    className="pointer-events-none absolute inset-y-0 -inset-x-[10px] rounded-[8px] bg-blue-100 animate-fact-flash motion-reduce:animate-none"
                  />
                )}
                <span className="relative">
                  <Mark status={status} required={required} />
                </span>
                <span className="relative">{key}</span>
              </dt>
              <dd className="relative flex min-w-0 flex-wrap items-start justify-end gap-[6px] text-right">
                <span
                  className={cn(
                    'min-w-0 break-keep text-caption [overflow-wrap:anywhere]',
                    settled
                      ? 'font-bold text-ink'
                      : required
                        ? 'font-medium text-pending'
                        : 'text-mute',
                  )}
                >
                  {required
                    ? '필요해요'
                    : (fact?.value ??
                      (status === '나중에' ? '나중에 정해요' : fact ? '미정' : '아직이에요'))}
                  {status === '확정' && <span className="sr-only"> · 확정</span>}
                </span>
                {status === '잠정' && (
                  <Chip tone="approved" size="sm">
                    잠정
                  </Chip>
                )}
                {status === '나중에' && (
                  <Chip tone="neutral" size="sm">
                    나중에
                  </Chip>
                )}
              </dd>
              {status === '잠정' && fact?.quote && (
                <dd className="relative col-span-2 break-keep pl-[27px] text-[11px] leading-[16px] text-mute [overflow-wrap:anywhere]">
                  「{fact.quote}」
                </dd>
              )}
            </div>
          )
        })}
      </dl>
      {children && <div className="flex flex-col gap-3 border-t border-line pt-4">{children}</div>}
    </Card>
  )
}
