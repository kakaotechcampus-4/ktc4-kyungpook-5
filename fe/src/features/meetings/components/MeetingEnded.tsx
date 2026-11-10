import { Link } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Tori } from '@/shared/ui/Tori'
import { candidateMeta } from '../confirmed'
import type { MeetingProcessingStep } from '../timeline'
import type { Suggestion } from '../types'
import type { MeetingReview } from '../types'
import { MeetingReviewPanel } from './MeetingReviewPanel'

const SHOWN = 3

function ProcessingStatus({ steps }: { steps: MeetingProcessingStep[] }) {
  const labels = { done: '완료', waiting: '확인 중', failed: '실패', empty: '없음' } as const
  const tones = { done: 'done', waiting: 'pending', failed: 'failed', empty: 'neutral' } as const
  return (
    <div className="rounded-[12px] border border-line bg-bg p-4" aria-label="회의 처리 상태">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-bold">처리 상태</h2>
        <span className="text-caption text-mute">단계별로 따로 확인해요</span>
      </div>
      <ul className="mt-3 divide-y divide-line">
        {steps.map((step) => (
          <li key={step.key} className="flex flex-wrap items-center gap-2 py-2 first:pt-0 last:pb-0">
            <span className="min-w-[88px] font-semibold">{step.label}</span>
            <Chip size="sm" tone={tones[step.state]}>{labels[step.state]}</Chip>
            <span className="text-caption text-ink2">{step.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function MeetingEnded({
  summary,
  suggestions,
  suggestionsError,
  extractionFailed,
  onRetry,
  onOpenCandidates,
  onOpenRecord,
  review,
  clubId,
  onStartReview,
  onSubmitReview,
  onSaveReviewNames,
  onCreateReviewDraft,
  onSaveReviewCandidates,
  reviewBusy,
  reviewError,
  reviewCandidatesSaved,
  processingSteps,
}: {
  summary: string
  suggestions: Suggestion[]
  suggestionsError: boolean
  extractionFailed: boolean
  onRetry: () => void
  onOpenCandidates: () => void
  onOpenRecord: () => void
  review?: MeetingReview
  clubId: string
  onStartReview?: () => void
  onSubmitReview?: () => void
  onSaveReviewNames?: (version: number, names: Record<string, string>, members: Record<string, { memberId: string | null; confirmed: boolean }>) => Promise<unknown>
  onCreateReviewDraft?: (version: number) => void
  onSaveReviewCandidates?: (version: number, requestId: string, candidates: Array<{ title: string; description: string | null; assigneeMemberId: string | null; dueDate: string | null; evidenceSegmentIds: string[] }>) => Promise<unknown>
  reviewBusy?: boolean
  reviewError?: unknown
  reviewCandidatesSaved?: boolean
  processingSteps: MeetingProcessingStep[]
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
              <p className="mt-3 text-caption text-ink2">
                확인한 후보만 먼저 저장돼요. 일정·알림 예약은 후보를 확인한 뒤 별도로 진행해요.
              </p>
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
            후보 확인·저장하기
          </Button>
        )}
        <Button variant="secondary" size="lg" className="mt-3 w-full" onClick={onOpenRecord}>
          회의 기록 보기
        </Button>
        <Link to="/meetings" className="mt-4 text-caption font-medium text-blue-700">
          새 회의 시작하기 ›
        </Link>
      </Card>
      <Card className="mx-auto max-w-[560px] p-5 text-left">
        <ProcessingStatus steps={processingSteps} />
      </Card>
      {onStartReview && onSubmitReview && onSaveReviewNames && onCreateReviewDraft && onSaveReviewCandidates && (
        <MeetingReviewPanel
          review={review}
          clubId={clubId}
          onStart={onStartReview}
          onSubmit={onSubmitReview}
          onSaveNames={onSaveReviewNames}
          onDraft={onCreateReviewDraft}
          onSaveCandidates={onSaveReviewCandidates}
          busy={reviewBusy ?? false}
          error={reviewError}
          candidatesSaved={reviewCandidatesSaved ?? false}
        />
      )}
    </div>
  )
}
