import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Chip } from '@/shared/ui/Chip'
import { useCreateMeeting, useMeetingData } from '../hooks'
import { meetingError } from '../errors'
import { MicControls } from '../audio'
import { Timeline } from './Timeline'
import { Suggestions, ConfirmedTasks } from './Suggestions'
const EMPTY: never[] = []
const statusLabel = {
  RECORDING: '진행 중',
  FINALIZING: '마지막 전사 처리 중',
  COMPLETED: '종료 · 저장 완료',
  FAILED: '처리 실패',
}
export function MeetingWorkspace({
  clubId,
  meetingId,
  highlightTaskId,
  records,
  notifications,
}: {
  clubId: string
  meetingId?: string
  highlightTaskId?: string
  records: ReactNode
  notifications: ReactNode
}) {
  const [audioActive, setAudioActive] = useState(false)
  const [title, setTitle] = useState('')
  const [consent, setConsent] = useState(false)
  const [resumeId, setResumeId] = useState('')
  const navigate = useNavigate()
  const create = useCreateMeeting(clubId)
  const data = useMeetingData(clubId, meetingId)
  const meeting = data.meeting.data
  if (meeting && meeting.clubId !== clubId)
    return (
      <Card className="space-y-3 p-6">
        <h1 className="text-h2">다른 소속의 회의입니다.</h1>
        <p>회의의 소속을 확인한 뒤 열어 주세요.</p>
        <Link
          className="text-blue-700 underline"
          to={`/meetings/${encodeURIComponent(meeting.id)}?clubId=${encodeURIComponent(meeting.clubId)}`}
        >
          이 회의의 소속으로 열기
        </Link>
      </Card>
    )
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1">{meeting?.title || '회의'}</h1>
          <p className="mt-2 text-ink2">회의를 듣고 자료와 다음 할 일을 함께 챙깁니다.</p>
        </div>
        {meeting && (
          <div className="flex items-center gap-3">
            <Chip tone={meeting.status === 'FAILED' ? 'failed' : 'neutral'}>
              {statusLabel[meeting.status]}
            </Chip>
            <Button variant="secondary" onClick={() => void data.refresh()}>
              새로고침
            </Button>
            <Link to="/meetings" className="text-caption underline">
              새 회의
            </Link>
          </div>
        )}
      </div>
      {!meetingId && (
        <Card className="p-6">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (consent)
                create.mutate(title.trim() || '회의', {
                  onSuccess: (m) => navigate(`/meetings/${encodeURIComponent(m.id)}`),
                })
            }}
          >
            <Input
              label="회의 이름"
              placeholder="예: 가을 워크숍 준비 회의"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              참여자에게 녹음과 전사 저장을 알리고 동의를 확인했습니다.
            </label>
            <Button type="submit" disabled={!consent || create.isPending}>
              {create.isPending ? '회의 만드는 중…' : '회의 만들기'}
            </Button>
            {create.error && (
              <p role="alert" className="text-failed">
                {meetingError(create.error)}
              </p>
            )}
          </form>
          <form
            className="mt-6 flex flex-wrap items-end gap-3 border-t border-line pt-5"
            onSubmit={(e) => {
              e.preventDefault()
              if (resumeId.trim()) navigate(`/meetings/${encodeURIComponent(resumeId.trim())}`)
            }}
          >
            <div className="min-w-0 flex-1">
              <Input
                label="이전 회의 ID로 열기"
                value={resumeId}
                onChange={(e) => setResumeId(e.target.value)}
              />
            </div>
            <Button type="submit" variant="secondary" disabled={!resumeId.trim()}>
              회의 열기
            </Button>
          </form>
        </Card>
      )}
      {data.meeting.isError && (
        <Card className="p-5 text-failed" role="alert">
          {meetingError(data.meeting.error)}
          <Button variant="secondary" className="ml-3" onClick={() => void data.refresh()}>
            다시 확인
          </Button>
        </Card>
      )}
      {meetingId && data.meeting.isPending && <p>회의 불러오는 중…</p>}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
        <div className="space-y-6">
          {meeting && (
            <>
              <Card className="p-5">
                <p className="text-caption text-mute">회의 ID: {meeting.id}</p>
                <p className="mt-2">
                  확정 전사만 표시합니다. 음성 전송과 마지막 전사 처리 상태를 확인해 주세요.
                </p>
                {(meeting.status === 'RECORDING' || meeting.status === 'FINALIZING') && (
                  <div className="mt-4">
                    <MicControls
                      meetingId={meeting.id}
                      onCompleted={() => void data.refresh()}
                      onRefresh={() => void data.refresh()}
                      onActiveChange={setAudioActive}
                    />
                  </div>
                )}
                {meeting.status === 'RECORDING' && !audioActive && (
                  <div className="mt-3 flex flex-wrap gap-3">
                    <Button
                      variant="secondary"
                      disabled={data.finish.isPending}
                      onClick={() => data.finish.mutate()}
                    >
                      마이크 없이 회의 종료
                    </Button>
                  </div>
                )}
                {data.finish.error && (
                  <p role="alert" className="mt-2 text-failed">
                    {meetingError(data.finish.error)}
                  </p>
                )}
              </Card>
              {(data.transcripts.isError || data.decisions.isError) && (
                <p className="text-failed" role="alert">
                  전사 또는 자료 답변을 갱신하지 못했습니다. 기존 내용은 유지됩니다.{' '}
                  <Button variant="secondary" onClick={() => void data.refresh()}>
                    다시 조회
                  </Button>
                </p>
              )}
              <Timeline
                key={meeting.id}
                transcripts={data.transcripts.data?.items ?? EMPTY}
                decisions={data.decisions.data ?? EMPTY}
                startedAt={meeting.startedAt}
                onRefresh={() => void data.refresh()}
              />
            </>
          )}
          {records}
          <ConfirmedTasks clubId={clubId} highlightTaskId={highlightTaskId} />
        </div>
        <aside className="space-y-6">
          {meeting && (
            <>
              {data.suggestionsQuery.isError && (
                <p role="alert" className="text-failed">
                  후보 목록을 확인하지 못했습니다. {meetingError(data.suggestionsQuery.error)}
                </p>
              )}
              <Suggestions
                clubId={clubId}
                suggestions={data.suggestions}
                onSaved={() => void data.refresh()}
              />
            </>
          )}
          {notifications}
        </aside>
      </div>
    </div>
  )
}
