import { Link } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Tori } from '@/shared/ui/Tori'
import { candidateMeta } from '../confirmed'
import type { Suggestion } from '../types'
import type { MeetingReview } from '../types'
import { MeetingReviewPanel } from './MeetingReviewPanel'

const SHOWN = 3

export function MeetingEnded({
  summary,
  suggestions,
  suggestionsError,
  extractionFailed,
  onRetry,
  onOpenCandidates,
  onOpenRecord,
  review,
  onStartReview,
  onSubmitReview,
  onSaveReviewNames,
  onCreateReviewDraft,
  reviewBusy,
  reviewError,
}: {
  summary: string
  suggestions: Suggestion[]
  suggestionsError: boolean
  extractionFailed: boolean
  onRetry: () => void
  onOpenCandidates: () => void
  onOpenRecord: () => void
  review?: MeetingReview
  onStartReview?: () => void
  onSubmitReview?: () => void
  onSaveReviewNames?: (version: number, names: Record<string, string>) => Promise<unknown>
  onCreateReviewDraft?: (version: number) => void
  reviewBusy?: boolean
  reviewError?: unknown
}) {
  return (
    <div className="mx-auto max-w-[1040px] space-y-6">
      <h1 className="text-h1">회의</h1>
      <Card className="mx-auto flex max-w-[560px] flex-col items-center px-7 pt-12 pb-8 text-center">
        <Tori size={88} />
        <h2 className="mt-6 text-[22px] font-bold">회의를 마쳤어요</h2>
        <p className="mt-2 text-caption text-ink2">{summary}</p>
        <div className="mt-6 w-full rounded-[12px] bg-bg p-4 text-left">
          <p className="flex items-center gap-2 text-caption font-bold">
            회의에서 나온 일정·할 일
            {!suggestionsError && <Chip tone="approved">{suggestions.length}건</Chip>}
          </p>
          {suggestionsError ? (
            <>
              <p className="mt-3 text-caption text-failed">
                후보를 불러오지 못했어요. 들은 말과 토리 답은 그대로 볼 수 있어요.
              </p>
              <button
                type="button"
                onClick={onRetry}
                className="mt-2 text-caption font-bold text-blue-700"
              >
                상태 다시 확인 ›
              </button>
            </>
          ) : suggestions.length ? (
            <>
              <ul className="mt-3 space-y-2">
                {suggestions.slice(0, SHOWN).map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-2">
                    <Chip>{s.kind === 'SCHEDULE' ? '일정' : '할 일'}</Chip>
                    <span className="font-bold">{s.title}</span>
                    <span className="text-caption text-ink2">{candidateMeta(s)}</span>
                  </li>
                ))}
              </ul>
              {suggestions.length > SHOWN && (
                <p className="mt-2 text-caption text-ink2">외 {suggestions.length - SHOWN}건</p>
              )}
              <p className="mt-3 text-caption text-ink2">확인한 후보만 저장되고 알림이 예약돼요.</p>
            </>
          ) : (
            !extractionFailed && (
              <p className="mt-3 text-caption text-ink2">회의에서 나온 일정·할 일이 없어요.</p>
            )
          )}
          {/* tasks.extract 오류는 '후보 없음'과 다르다(⑫). */}
          {!suggestionsError && extractionFailed && (
            <>
              <p className="mt-3 text-caption text-failed">
                {suggestions.length
                  ? '일부 말에서 후보를 뽑지 못했어요.'
                  : '후보를 뽑지 못했어요. 들은 말과 토리 답은 그대로 볼 수 있어요.'}
              </p>
              <button
                type="button"
                onClick={onRetry}
                className="mt-2 text-caption font-bold text-blue-700"
              >
                상태 다시 확인 ›
              </button>
            </>
          )}
        </div>
        {suggestions.length > 0 && (
          <Button size="lg" className="mt-5 w-full" onClick={onOpenCandidates}>
            후보 확인하기
          </Button>
        )}
        <Button variant="secondary" size="lg" className="mt-3 w-full" onClick={onOpenRecord}>
          회의 기록 보기
        </Button>
        <Link to="/meetings" className="mt-4 text-caption font-medium text-blue-700">
          새 회의 시작하기 ›
        </Link>
      </Card>
      {onStartReview && onSubmitReview && onSaveReviewNames && onCreateReviewDraft && (
        <MeetingReviewPanel
          review={review}
          onStart={onStartReview}
          onSubmit={onSubmitReview}
          onSaveNames={onSaveReviewNames}
          onDraft={onCreateReviewDraft}
          busy={reviewBusy ?? false}
          error={reviewError}
        />
      )}
    </div>
  )
}
