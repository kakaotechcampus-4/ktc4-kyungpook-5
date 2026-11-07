import { Link } from 'react-router-dom'
import { useMeetings } from '../hooks'
import { meetingWhen } from '../timeline'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { MEETING_STATUS_LABEL, MEETING_STATUS_TONE } from '@/shared/lib/labels'

export function MeetingList({ clubId }: { clubId: string }) {
  const query = useMeetings(clubId)
  const meetings = query.data?.data ?? []
  return (
    <Card className="p-6">
      <h2 className="text-h2">지난 회의</h2>
      {query.isPending && (
        <p role="status" className="mt-4 text-caption text-mute">
          지난 회의를 불러오는 중이에요.
        </p>
      )}
      {query.isError && (
        <p role="alert" className="mt-4 text-caption text-failed">
          지난 회의를 불러오지 못했어요.{' '}
          <button
            type="button"
            className="font-bold underline"
            onClick={() => void query.refetch()}
          >
            다시 불러오기
          </button>
        </p>
      )}
      {query.isSuccess && meetings.length === 0 && (
        <p className="mt-4 text-caption text-mute">아직 회의가 없어요. 첫 회의를 시작해 보세요.</p>
      )}
      {meetings.length > 0 && (
        <ul
          aria-label="지난 회의 목록"
          className="mt-3 max-h-[420px] divide-y divide-line overflow-y-auto border-t border-line"
        >
          {meetings.map((meeting) => (
            <li key={meeting.id}>
              <Link
                to={`/meetings/${encodeURIComponent(meeting.id)}`}
                className="flex items-center gap-3 px-1 py-3.5 transition-colors hover:bg-bg focus-visible:outline-2 focus-visible:outline-blue-600"
              >
                <span className="min-w-0 flex-1">
                  <strong className="block truncate text-[15px] font-medium">
                    {meeting.title || '제목 없는 회의'}
                  </strong>
                  <span className="mt-0.5 block text-caption text-ink2">
                    {meetingWhen(meeting)}
                  </span>
                </span>
                <Chip tone={MEETING_STATUS_TONE[meeting.status]}>
                  {meeting.status === 'RECORDING' && (
                    <span aria-hidden className="mr-1.5 size-1.5 rounded-full bg-[#c4574d]" />
                  )}
                  {MEETING_STATUS_LABEL[meeting.status]}
                </Chip>
                <span aria-hidden className="text-ink2">
                  ›
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
