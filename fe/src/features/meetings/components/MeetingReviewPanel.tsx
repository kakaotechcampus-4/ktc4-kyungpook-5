import { useEffect, useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { meetingError } from '../errors'
import type { MeetingReview } from '../types'

export function MeetingReviewPanel({
  review,
  onStart,
  onSubmit,
  onSaveNames,
  onDraft,
  busy,
  error,
}: {
  review: MeetingReview | undefined
  onStart: () => void
  onSubmit: () => void
  onSaveNames: (version: number, names: Record<string, string>) => void
  onDraft: (version: number) => void
  busy: boolean
  error: unknown
}) {
  const [names, setNames] = useState<Record<string, string>>({})
  const errorMessage = error ? meetingError(error) : null
  useEffect(() => {
    if (review) setNames(Object.fromEntries(review.speakers.map((speaker) => [speaker.label, speaker.name ?? ''])))
  }, [review])
  if (!review) {
    return <Card className="space-y-3 p-5"><h2 className="text-h2">회의 후 화자 확인</h2><p>회의가 끝났습니다. 녹음에서 화자를 나눈 뒤 이름을 확인할 수 있어요.</p><Button onClick={onStart} disabled={busy}>화자분리 검토 시작</Button>{errorMessage && <p role="alert" className="text-failed">{errorMessage}</p>}</Card>
  }
  const ready = review.status === 'NEEDS_REVIEW' || review.status === 'DRAFT_READY'
  return <Card className="space-y-4 p-5">
    <div><h2 className="text-h2">회의 후 화자 확인</h2><p className="mt-1 text-ink2">화자와 할 일 담당자는 다를 수 있어요. 이름과 후보를 확인한 뒤 저장하세요.</p></div>
    {review.status === 'QUEUED' && <Button onClick={onSubmit} disabled={busy}>화자분리 실행</Button>}
    {(review.status === 'SUBMITTING' || review.status === 'PROCESSING') && <p role="status">화자분리 결과를 기다리는 중입니다… 새로고침해도 작업은 이어집니다.</p>}
    {review.status === 'FAILED' && <><p role="alert" className="text-failed">화자분리를 완료하지 못했습니다. 원래 전사는 보존됩니다. {review.errorCode ?? ''}</p><Button onClick={onSubmit} disabled={busy}>다시 시도</Button></>}
    {ready && <>
      <div className="space-y-3">{review.speakers.map((speaker) => <Input key={speaker.label} label={speaker.label} placeholder="실제 이름 또는 비워 두기" value={names[speaker.label] ?? ''} onChange={(event) => setNames((current) => ({ ...current, [speaker.label]: event.target.value }))} />)}</div>
      <Button variant="secondary" onClick={() => onSaveNames(review.version, names)} disabled={busy}>화자 이름 저장</Button>
      <div className="space-y-2 border-t border-line pt-4"><h3 className="font-semibold">화자별 전사</h3>{review.segments.map((segment) => <p key={segment.segmentId} className="text-sm"><strong>{segment.speakerLabel ? names[segment.speakerLabel] || segment.speakerLabel : '확인 필요'}:</strong> {segment.text}</p>)}</div>
      {review.status === 'NEEDS_REVIEW' && <Button onClick={() => onDraft(review.version)} disabled={busy}>회의록·할 일 후보 만들기</Button>}
    </>}
    {review.draft && <div className="space-y-3 border-t border-line pt-4"><h3 className="font-semibold">확인할 회의록과 할 일 후보</h3>{review.draft.summary.map((item) => <p key={item.text}>• {item.text}</p>)}{review.draft.tasks.map((task) => <p key={task.title}>• {task.title} · 담당 후보: {task.suggestedAssignee ?? '미지정'}</p>)}<p className="text-caption text-ink2">후보는 아직 저장·예약·알림하지 않았습니다. 담당자·내용·기한을 확인한 뒤 확정하세요.</p></div>}
    {errorMessage && <p role="alert" className="text-failed">{errorMessage}</p>}
  </Card>
}
