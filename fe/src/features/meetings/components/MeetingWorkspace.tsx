import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { useMeetingData } from '../hooks'
import { MeetingList } from './MeetingList'
import { MeetingStart, type MeetingEventOption } from './MeetingStart'
import { MeetingToriPanel } from './MeetingToriPanel'
import type { AudioPhase } from '../audio/useMeetingAudio'
import { meetingError } from '../errors'
import { meetingAudioVisible, meetingToriVisible } from '../timeline'
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
  events,
  notifications,
}: {
  clubId: string
  meetingId?: string
  highlightTaskId?: string
  events: MeetingEventOption[]
  notifications: ReactNode
}) {
  const [audioActive, setAudioActive] = useState(false)
  const [audioPhase, setAudioPhase] = useState<AudioPhase>('idle')
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
  if (!meetingId)
    return (
      <div className="mx-auto max-w-[1040px] space-y-6">
        <h1 className="text-h1">회의</h1>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:grid-cols-[minmax(0,1fr)_400px]">
          <MeetingStart clubId={clubId} events={events} />
          <MeetingList clubId={clubId} />
        </div>
        <div className="grid items-start gap-6 border-t border-line pt-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] xl:grid-cols-[minmax(0,1fr)_400px]">
          <ConfirmedTasks clubId={clubId} highlightTaskId={highlightTaskId} />
          {notifications}
        </div>
      </div>
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
            <Chip tone={meeting.status === 'FAILED' && !audioActive ? 'failed' : 'neutral'}>
              {audioActive && (meeting.status === 'COMPLETED' || meeting.status === 'FAILED')
                ? '마지막 응답 확인 중'
                : statusLabel[meeting.status]}
            </Chip>
            <Button variant="secondary" onClick={() => void data.refresh()}>
              새로고침
            </Button>
            {!audioActive && (
              <Link to="/meetings" className="text-caption underline">
                새 회의
              </Link>
            )}
          </div>
        )}
      </div>
      {meeting && meetingToriVisible(meeting.status, audioActive) ? (
        <MeetingToriPanel
          meeting={meeting}
          phase={audioPhase}
          audioActive={audioActive}
          transcripts={data.transcripts.data?.items ?? EMPTY}
          decisions={data.decisions.data ?? EMPTY}
          loading={data.transcripts.isPending || data.decisions.isPending}
          error={data.transcripts.isError || data.decisions.isError}
          onRefresh={() => void data.refresh()}
        />
      ) : null}
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
                {meetingAudioVisible(meeting.status, audioActive) && (
                  <div className="mt-4">
                    <MicControls
                      meetingId={meeting.id}
                      onCompleted={() => void data.refresh()}
                      onRefresh={() => void data.refresh()}
                      onActiveChange={setAudioActive}
                      onPhaseChange={setAudioPhase}
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
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-h2">전사와 자료 답변</h2>
                <a
                  href="#meeting-suggestions"
                  className="text-caption font-semibold text-blue-700 underline underline-offset-4 xl:hidden"
                >
                  일정·할 일 후보 보기
                </a>
              </div>
              <Timeline
                key={meeting.id}
                transcripts={data.transcripts.data?.items ?? EMPTY}
                decisions={data.decisions.data ?? EMPTY}
                startedAt={meeting.startedAt}
                onRefresh={() => void data.refresh()}
              />
            </>
          )}
          <ConfirmedTasks clubId={clubId} highlightTaskId={highlightTaskId} />
        </div>
        <aside id="meeting-suggestions" className="scroll-mt-24 space-y-6">
          {meeting && (
            <>
              {data.suggestionsQuery.isError && (
                <p role="alert" className="text-failed">
                  후보 목록을 확인하지 못했습니다. {meetingError(data.suggestionsQuery.error)}
                </p>
              )}
              {data.suggestionsQuery.isPending ? (
                <p role="status">후보 목록을 불러오는 중입니다…</p>
              ) : !data.suggestionsQuery.isError ? (
                <Suggestions
                  clubId={clubId}
                  suggestions={data.suggestions}
                  onSaved={() => void data.refresh()}
                />
              ) : null}
            </>
          )}
          {notifications}
        </aside>
      </div>
    </div>
  )
}
