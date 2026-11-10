import { useEffect, useRef, useState } from 'react'
import { useClubMembers } from '@/features/clubs/hooks'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input, Textarea } from '@/shared/ui/Input'
import { meetingCodeMessage, meetingError } from '../errors'
import { meetingsApi } from '../api'
import type { MeetingReview, MeetingReviewTask } from '../types'

type Candidate = MeetingReviewTask & { assigneeMemberId: string | null }
export function MeetingReviewPanel({ review, clubId, onStart, onSubmit, onSaveNames, onDraft, onSaveCandidates, busy, error, candidatesSaved }: { review: MeetingReview | undefined; clubId: string; candidatesSaved: boolean; onStart: () => void; onSubmit: () => void; onSaveNames: (version: number, names: Record<string, string>, members: Record<string, { memberId: string | null; confirmed: boolean }>) => Promise<unknown>; onDraft: (version: number) => void; onSaveCandidates: (version: number, requestId: string, candidates: Candidate[]) => Promise<unknown>; busy: boolean; error: unknown }) {
  const members = useClubMembers(clubId)
  const [names, setNames] = useState<Record<string, string>>({})
  const [speakerMembers, setSpeakerMembers] = useState<Record<string, string>>({})
  const [savedVersion, setSavedVersion] = useState<number | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [saveError, setSaveError] = useState('')
  const [candidateError, setCandidateError] = useState('')
  const requestId = useRef(crypto.randomUUID())
  const [playing, setPlaying] = useState<string | null>(null)
  const loaded = useRef<{ speakers: string; draft: string } | null>(null)
  const errorMessage = saveError || candidateError || (error ? meetingError(error) : null)
  // 충돌·다른 저장으로 version만 바뀐 새로고침에는 입력을 지키고, 서버 내용이 바뀐 칸만 다시 채운다(#377).
  useEffect(() => { if (!review) return; const speakers = JSON.stringify(review.speakers); const draft = JSON.stringify(review.draft?.tasks ?? null); const previous = loaded.current; loaded.current = { speakers, draft }; if (previous?.speakers !== speakers) { setNames(Object.fromEntries(review.speakers.map((speaker) => [speaker.label, speaker.name ?? '']))); setSpeakerMembers(Object.fromEntries(review.speakers.map((speaker) => [speaker.label, speaker.memberId ?? '']))); setSavedVersion(review.speakers.length > 0 && review.speakers.every((speaker) => speaker.confirmed === true) ? review.version : null) } else setSavedVersion((saved) => saved === null ? null : review.version); if (previous?.draft !== draft) setCandidates((review.draft?.tasks ?? []).map((task) => ({ ...task, assigneeMemberId: task.suggestedAssigneeMemberId }))) }, [review])
  if (!review) return <Card className="space-y-3 p-5"><h2 className="text-h2">회의 후 화자 확인</h2><p>회의가 끝났습니다. 녹음에서 화자를 나눈 뒤 이름을 확인할 수 있어요.</p><Button onClick={onStart} disabled={busy}>화자분리 검토 시작</Button>{errorMessage && <p role="alert" className="text-failed">{errorMessage}</p>}</Card>
  const ready = review.status === 'NEEDS_REVIEW' || review.status === 'DRAFT_READY'
  const namesSaved = savedVersion === review.version
  const saveNames = async () => { setSaveError(''); try { await onSaveNames(review.version, names, Object.fromEntries(review.speakers.map((speaker) => [speaker.label, { memberId: speakerMembers[speaker.label] || null, confirmed: Boolean(speakerMembers[speaker.label] || names[speaker.label]) }]))); setSavedVersion(review.version) } catch (cause) { setSaveError(meetingError(cause)) } }
  const play = async (segmentId: string) => { setPlaying(segmentId); let url: string | undefined; try { const blob = await meetingsApi.reviewSegmentClip(review.meetingId, segmentId); url = URL.createObjectURL(blob); const audio = new Audio(url); await audio.play(); await new Promise<void>((resolve, reject) => { audio.onended = () => resolve(); audio.onerror = () => reject(new Error('음성 재생에 실패했습니다.')) }) } catch (cause) { setSaveError(url ? '음성 구간을 재생하지 못했어요. 이 브라우저에서 소리를 재생할 수 있는지 확인해 주세요.' : `음성 구간을 불러오지 못했어요. ${meetingError(cause)}`) } finally { if (url) URL.revokeObjectURL(url); setPlaying(null) } }
  const updateCandidate = (index: number, changes: Partial<Candidate>) => setCandidates((current) => current.map((candidate, i) => i === index ? { ...candidate, ...changes } : candidate))
  const saveCandidates = async () => { setCandidateError(''); try { await onSaveCandidates(review.version, requestId.current, candidates) } catch (cause) { setCandidateError(meetingError(cause)) } }
  return <Card className="space-y-4 p-5">
    <div><h2 className="text-h2">회의 후 화자 확인</h2><p className="mt-1 text-ink2">화자와 할 일 담당자는 다를 수 있어요. 이름과 후보를 확인한 뒤 저장하세요.</p></div>
    {review.status === 'QUEUED' && <Button onClick={onSubmit} disabled={busy}>화자분리 실행</Button>}
    {(review.status === 'SUBMITTING' || review.status === 'PROCESSING') && <p role="status">화자분리 결과를 기다리는 중입니다… 새로고침해도 작업은 이어집니다.</p>}
    {review.status === 'FAILED' && <><p role="alert" className="text-failed">화자분리를 완료하지 못했습니다. 원래 전사는 보존됩니다. {review.errorCode && meetingCodeMessage(review.errorCode)}</p><Button onClick={onSubmit} disabled={busy}>다시 시도</Button></>}
    {review.status === 'SUBMISSION_UNKNOWN' && <p role="alert" className="text-failed">화자분리 제출 결과를 확인하지 못했습니다. 중복 제출을 막기 위해 잠시 뒤 새로고침해 상태를 확인해 주세요.</p>}
    {ready && <>
      <div className="space-y-3">{review.speakers.map((speaker) => <div key={speaker.label} className="space-y-2 rounded-lg border border-line p-3"><Input label={`${speaker.label} 이름 (선택)`} placeholder="미확인으로 두기" value={names[speaker.label] ?? ''} onChange={(event) => { setNames((current) => ({ ...current, [speaker.label]: event.target.value })); setSavedVersion(null); setSaveError('') }} /><label className="text-caption font-bold">실제 구성원<select className="mt-2 w-full rounded-lg border border-soft bg-bg p-3" value={speakerMembers[speaker.label] ?? ''} onChange={(event) => { setSpeakerMembers((current) => ({ ...current, [speaker.label]: event.target.value })); setSavedVersion(null) }}><option value="">미확인</option>{members.data?.map((member) => <option key={member.id} value={member.id}>{member.name}</option>)}</select></label><p className="text-caption text-mute">{speaker.confirmed ? '저장된 확인' : '저장 전 확인 필요'}</p></div>)}</div>
      <div className="flex flex-wrap items-center gap-3"><Button variant="secondary" onClick={() => void saveNames()} disabled={busy || namesSaved}>화자 이름·구성원 저장</Button>{!namesSaved && <span className="text-caption text-pending">변경 내용을 저장해야 후보를 만들 수 있어요.</span>}</div>
      <div className="space-y-2 border-t border-line pt-4"><h3 className="font-semibold">화자별 전사</h3>{review.segments.map((segment) => <div key={segment.segmentId} className="flex items-start gap-2"><p className="min-w-0 flex-1 break-words text-sm"><strong>{segment.speakerLabel ? names[segment.speakerLabel] || segment.speakerLabel : '화자 미확인'}:</strong> {segment.text}</p><Button size="sm" variant="ghost" disabled={playing !== null} onClick={() => void play(segment.segmentId)}>{playing === segment.segmentId ? '재생 중…' : '듣기'}</Button></div>)}</div>
      {review.status === 'NEEDS_REVIEW' && <Button onClick={() => onDraft(review.version)} disabled={busy || !namesSaved}>회의록·할 일 후보 만들기</Button>}
    </>}
    {review.draft && <div className="space-y-3 border-t border-line pt-4"><h3 className="font-semibold">확인할 회의록과 할 일 후보</h3>{review.draft.summary.map((item) => <p key={item.text}>• {item.text}</p>)}{candidates.map((candidate, index) => <div key={`${candidate.title}-${index}`} className="space-y-2 rounded-lg border border-line p-3"><Input label="후보 내용" value={candidate.title} onChange={(e) => updateCandidate(index, { title: e.target.value })} /><Textarea label="설명" value={candidate.description ?? ''} onChange={(e) => updateCandidate(index, { description: e.target.value })} /><label className="text-caption font-bold">담당자<select className="mt-2 w-full rounded-lg border border-soft bg-bg p-3" value={candidate.assigneeMemberId ?? ''} onChange={(e) => updateCandidate(index, { assigneeMemberId: e.target.value || null })}><option value="">담당자 미지정</option>{members.data?.map((member) => <option key={member.id} value={member.id}>{member.name}</option>)}</select></label><Input label="기한" type="date" value={candidate.dueDate ?? ''} onChange={(e) => updateCandidate(index, { dueDate: e.target.value || null })} /><p className="text-caption text-mute">근거 전사 {candidate.evidenceSegmentIds.length}건</p></div>)}<p className="text-caption text-ink2">저장 전에는 일정 예약이나 Push 발송이 없습니다.</p>{candidatesSaved ? <p role="status" className="text-caption font-bold text-done">후보를 저장했어요. 이 회의의 후보는 한 번만 저장할 수 있어요.</p> : candidates.length > 0 && <Button onClick={() => void saveCandidates()} disabled={busy || !namesSaved}>확인한 후보 저장</Button>}</div>}
    {errorMessage && <p role="alert" className="text-failed">{errorMessage}{ready && ' 입력한 내용은 유지됩니다.'}</p>}
  </Card>
}
