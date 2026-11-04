import { useEffect, useRef, useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { meetingError } from '../errors'
import type { MeetingReview } from '../types'

export function MeetingReviewPanel({ review, onStart, onSubmit, onSaveNames, onDraft, busy, error }: { review: MeetingReview | undefined; onStart: () => void; onSubmit: () => void; onSaveNames: (version: number, names: Record<string, string>) => Promise<unknown>; onDraft: (version: number) => void; busy: boolean; error: unknown }) {
  const [names, setNames] = useState<Record<string, string>>({})
  const [savedVersion, setSavedVersion] = useState<number | null>(null)
  const [saveError, setSaveError] = useState('')
  const loaded = useRef<string | null>(null)
  const errorMessage = saveError || (error ? meetingError(error) : null)
  useEffect(() => { if (!review) return; const key = `${review.id}:${review.version}`; if (loaded.current === key) return; loaded.current = key; setNames(Object.fromEntries(review.speakers.map((speaker) => [speaker.label, speaker.name ?? '']))); setSavedVersion(review.version); setSaveError('') }, [review])
  if (!review) return <Card className="space-y-3 p-5"><h2 className="text-h2">회의 후 화자 확인</h2><p>회의가 끝났습니다. 녹음에서 화자를 나눈 뒤 이름을 확인할 수 있어요.</p><Button onClick={onStart} disabled={busy}>화자분리 검토 시작</Button>{errorMessage && <p role="alert" className="text-failed">{errorMessage}</p>}</Card>
  const ready = review.status === 'NEEDS_REVIEW' || review.status === 'DRAFT_READY'
  const namesSaved = savedVersion === review.version
  const saveNames = async () => { setSaveError(''); try { await onSaveNames(review.version, names); setSavedVersion(review.version) } catch (cause) { setSaveError(meetingError(cause)) } }
  return <Card className="space-y-4 p-5">
    <div><h2 className="text-h2">회의 후 화자 확인</h2><p className="mt-1 text-ink2">화자와 할 일 담당자는 다를 수 있어요. 이름을 확인한 뒤 저장하세요. 이름을 모르면 비워 둘 수 있어요.</p></div>
    {review.status === 'QUEUED' && <Button onClick={onSubmit} disabled={busy}>화자분리 실행</Button>}
    {(review.status === 'SUBMITTING' || review.status === 'PROCESSING') && <p role="status">화자분리 결과를 기다리는 중입니다… 새로고침해도 작업은 이어집니다.</p>}
    {review.status === 'FAILED' && <><p role="alert" className="text-failed">화자분리를 완료하지 못했습니다. 원래 전사는 보존됩니다. {review.errorCode ?? ''}</p><Button onClick={onSubmit} disabled={busy}>다시 시도</Button></>}
    {ready && <>
      <div className="space-y-3">{review.speakers.map((speaker) => <Input key={speaker.label} label={`${speaker.label} 이름 (선택)`} placeholder="미확인으로 두기" value={names[speaker.label] ?? ''} onChange={(event) => { setNames((current) => ({ ...current, [speaker.label]: event.target.value })); setSavedVersion(null); setSaveError('') }} />)}</div>
      <div className="flex flex-wrap items-center gap-3"><Button variant="secondary" onClick={() => void saveNames()} disabled={busy || namesSaved}>화자 이름 저장</Button>{!namesSaved && <span className="text-caption text-pending">변경 내용을 저장해야 후보를 만들 수 있어요.</span>}</div>
      <div className="space-y-2 border-t border-line pt-4"><h3 className="font-semibold">화자별 전사</h3>{review.segments.map((segment) => <p key={segment.segmentId} className="break-words text-sm"><strong>{segment.speakerLabel ? names[segment.speakerLabel] || segment.speakerLabel : '화자 미확인'}:</strong> {segment.text}</p>)}</div>
      {review.status === 'NEEDS_REVIEW' && <Button onClick={() => onDraft(review.version)} disabled={busy || !namesSaved}>회의록·할 일 후보 만들기</Button>}
    </>}
    {review.draft && <div className="space-y-3 border-t border-line pt-4"><h3 className="font-semibold">확인할 회의록과 할 일 후보</h3>{review.draft.summary.map((item) => <p key={item.text}>• {item.text}</p>)}{review.draft.tasks.map((task) => <p key={task.title}>• {task.title} · 담당 후보: {task.suggestedAssignee ?? '미지정'}</p>)}<p className="text-caption text-ink2">후보는 아직 저장·예약·알림하지 않았습니다. 담당자·내용·기한을 확인한 뒤 확정하세요.</p></div>}
    {errorMessage && <p role="alert" className="text-failed">{errorMessage} 입력한 이름은 유지됩니다. 저장을 다시 시도해 주세요.</p>}
  </Card>
}
