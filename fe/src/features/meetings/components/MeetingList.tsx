import { Link } from 'react-router-dom'
import { useMeetings } from '../hooks'
import type { Meeting } from '../types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

const STATUS_LABEL: Record<Meeting['status'], string> = {
  RECORDING: '진행 중',
  FINALIZING: '마지막 처리 중',
  COMPLETED: '종료됨',
  FAILED: '처리 실패',
}

function formatDate(value: string | null) {
  if (!value) return '시각 미정'
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function MeetingList({ clubId, selectedId }: { clubId: string; selectedId?: string }) {
  const query = useMeetings(clubId)
  const meetings = query.data?.data ?? []
  return (
    <Card className="space-y-4 p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-h2">최근 회의</h2>
          <p className="mt-1 text-caption text-mute">선택한 소속의 저장된 회의를 엽니다.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void query.refetch()}>
          새로고침
        </Button>
      </div>
      {query.isPending && <p role="status">회의 목록을 불러오는 중이에요.</p>}
      {query.isError && (
        <p role="alert" className="text-failed">
          회의 목록을 불러오지 못했어요. 다시 시도해 주세요.
        </p>
      )}
      {query.isSuccess && meetings.length === 0 && (
        <p className="text-mute">저장된 회의가 없어요. 새 회의를 만들어 보세요.</p>
      )}
      {meetings.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2">
          {meetings.map((meeting) => (
            <li key={meeting.id}>
              <Link
                to={`/meetings/${encodeURIComponent(meeting.id)}`}
                aria-current={selectedId === meeting.id ? 'page' : undefined}
                className={`block rounded-lg border p-3 transition-colors hover:bg-bg ${
                  selectedId === meeting.id ? 'border-blue-600 bg-blue-50' : 'border-line'
                }`}
              >
                <strong className="block truncate">{meeting.title || '제목 없는 회의'}</strong>
                <span className="mt-1 block text-caption text-mute">
                  {STATUS_LABEL[meeting.status]} · {formatDate(meeting.startedAt ?? meeting.endedAt)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
