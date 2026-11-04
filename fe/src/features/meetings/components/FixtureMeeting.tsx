import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { MeetingBanner, MeetingHeader, StatusPill } from './MeetingHeader'
import { ToriColumn, TranscriptColumn } from './MeetingColumns'
import { MeetingEnded } from './MeetingEnded'
import { CandidatesModal } from './Suggestions'
import { EndMeetingModal } from './MeetingConfirm'
import { fixtureDecisions, fixtureMeeting, fixtureSuggestion, fixtureTranscripts } from '../fixture'

// 개발용: 서버와 마이크 없이 회의 중 화면 모양만 본다.
export function FixtureMeeting() {
  const now = Date.parse(fixtureMeeting.startedAt!) + 6 * 60_000
  const [params] = useSearchParams()
  const [candidatesOpen, setCandidatesOpen] = useState(false)
  const [endOpen, setEndOpen] = useState(false)
  if (params.get('ended') === '1')
    return (
      <>
        <MeetingEnded
          clubId={fixtureMeeting.clubId}
          summary={`${fixtureMeeting.title} · 14:00 – 14:06 · 들은 말 4개 · 토리 2번`}
          suggestions={[fixtureSuggestion]}
          suggestionsError={false}
          extractionFailed={false}
          onRetry={() => undefined}
          onOpenCandidates={() => setCandidatesOpen(true)}
          onOpenRecord={() => undefined}
        />
        <CandidatesModal
          open={candidatesOpen}
          onClose={() => setCandidatesOpen(false)}
          clubId={fixtureMeeting.clubId}
          suggestions={[fixtureSuggestion]}
          onSaved={() => undefined}
        />
      </>
    )
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4 lg:h-[calc(100dvh-72px)]">
      <MeetingBanner tone="pending" title="개발 fixture · 서버와 마이크에 연결하지 않은 예시">
        회의 끝내기는 확인 창만 열어요.{' '}
        <Link to="/meetings" className="underline">
          실제 회의로 돌아가기
        </Link>
      </MeetingBanner>
      <MeetingHeader
        title={fixtureMeeting.title ?? '회의'}
        pills={
          <StatusPill kind="recording">
            녹음 중 <span className="tabular-nums">6:12</span>
          </StatusPill>
        }
        meta="14:00 시작 · 후보 1건 · 토리 2번"
        actions={
          <>
            <Button variant="secondary">일시정지</Button>
            <Button onClick={() => setEndOpen(true)}>회의 끝내기</Button>
          </>
        }
      />
      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] xl:grid-cols-[420px_minmax(0,1fr)]">
        <TranscriptColumn
          className="max-h-[60vh] lg:max-h-none"
          transcripts={fixtureTranscripts}
          decisions={fixtureDecisions}
          startedAt={fixtureMeeting.startedAt}
          live
        />
        <ToriColumn
          className="max-h-[70vh] lg:max-h-none"
          transcripts={fixtureTranscripts}
          decisions={fixtureDecisions}
          startedAt={fixtureMeeting.startedAt}
          ongoing
          now={now}
          loading={false}
          error={false}
          onRefresh={() => undefined}
        />
      </div>
      <EndMeetingModal
        open={endOpen}
        subtitle={`${fixtureMeeting.title} · 6:12 녹음 · 들은 말 4개`}
        heard={4}
        answered={2}
        recording
        busy={false}
        onClose={() => setEndOpen(false)}
        onConfirm={() => setEndOpen(false)}
      />
    </div>
  )
}
