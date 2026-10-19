import type { ReactNode } from 'react'
import { Button } from '@/shared/ui/Button'
import { Tori } from '@/shared/ui/Tori'

interface CoachMarkProps {
  step: number
  title: string
  children: ReactNode
  onClose: () => void
  onPrevious?: () => void
  onNext?: () => void
  nextLabel?: string
  nextDisabled?: boolean
}

export function CoachMark({
  step,
  title,
  children,
  onClose,
  onPrevious,
  onNext,
  nextLabel = '다음',
  nextDisabled,
}: CoachMarkProps) {
  return (
    <section
      data-onboarding-coach
      aria-label="토리의 시작 안내"
      className="relative mb-6 rounded-2xl border border-blue-200 bg-blue-50 p-4 sm:p-5"
    >
      <div className="flex items-start gap-3">
        <Tori size={38} />
        <div className="min-w-0 flex-1">
          <p className="mb-1 text-[11px] font-bold text-blue-600" role="status">
            토리의 시작 안내 · {step} / 5
          </p>
          <h2 className="text-h3 text-blue-900">{title}</h2>
          <div className="mt-2 text-[13px] leading-6 text-blue-900">{children}</div>
        </div>
        <button
          type="button"
          aria-label="시작 안내 닫기"
          onClick={onClose}
          className="rounded-lg px-2 py-1 text-blue-700 hover:bg-blue-100"
        >
          ✕
        </button>
      </div>
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-blue-200 pt-3">
        <div className="flex gap-1" aria-hidden>
          {[1, 2, 3, 4, 5].map((item) => (
            <span
              key={item}
              className={`h-1.5 w-5 rounded-full ${item <= step ? 'bg-blue-600' : 'bg-blue-200'}`}
            />
          ))}
        </div>
        <div className="flex gap-2">
          {onPrevious && (
            <Button size="sm" variant="ghost" onClick={onPrevious}>
              이전
            </Button>
          )}
          {onNext && (
            <Button size="sm" disabled={nextDisabled} onClick={onNext}>
              {nextLabel}
            </Button>
          )}
        </div>
      </div>
      <span
        aria-hidden
        className="absolute -bottom-2 left-8 size-4 rotate-45 border-r border-b border-blue-200 bg-blue-50"
      />
    </section>
  )
}
