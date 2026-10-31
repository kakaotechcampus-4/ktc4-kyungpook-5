import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Chip } from '@/shared/ui/Chip'
import { Timeline } from './Timeline'
import { fixtureDecisions, fixtureMeeting, fixtureSuggestion, fixtureTranscripts } from '../fixture'
export function FixtureMeeting() {
  const [title, setTitle] = useState(fixtureSuggestion.title)
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="rounded-xl border border-pending-line bg-pending-bg p-4">
        <strong>개발 fixture · 서버와 마이크에 연결하지 않은 예시</strong>
        <p className="mt-1">
          입력은 이 화면에서만 바뀝니다. 실제 저장·예약·알림은 생성되지 않습니다.
        </p>
        <Link to="/meetings" className="mt-2 inline-block underline">
          실제 회의로 돌아가기
        </Link>
      </div>
      <div>
        <Chip>개발 예시</Chip>
        <h1 className="mt-3 text-h1">{fixtureMeeting.title}</h1>
        <p className="mt-2 text-ink2">
          전사가 본문입니다. 늦은 답은 아래에 원래 시각을 표시합니다.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Timeline
          transcripts={fixtureTranscripts}
          decisions={fixtureDecisions}
          startedAt={fixtureMeeting.startedAt}
          onRefresh={() => undefined}
        />
        <aside className="space-y-4">
          <Card className="space-y-3 p-5">
            <h2 className="text-h2">확인할 일정·할 일</h2>
            <Input label="후보 내용" value={title} onChange={(e) => setTitle(e.target.value)} />
            <Input
              label="후보 담당 이름 · 계정 확인 필요"
              defaultValue={fixtureSuggestion.suggestedAssignee ?? ''}
            />
            <Input
              label="마감 시각 · 한국시간"
              type="datetime-local"
              defaultValue="2026-10-20T15:00"
            />
            <Input label="알림 시각 · 한국시간" type="datetime-local" />
            <p className="text-caption text-mute">
              실제 소속 계정 선택·확인 후 서버가 저장·예약합니다. 이 예시에는 저장 버튼이 없습니다.
            </p>
          </Card>
          <Card className="border-failed-line p-4">
            <p className="text-failed">도구 실패 예시 · 찾지 못했어요</p>
            <p className="mt-2 text-caption">
              위의 ‘기록에 없음’은 정상 조회 결과이고 이 상태는 도구 오류입니다.
            </p>
          </Card>
        </aside>
      </div>
    </div>
  )
}
