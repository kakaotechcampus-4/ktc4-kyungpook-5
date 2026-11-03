import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMe, useNotificationClub } from '@/features/auth/hooks'
import { MeetingWorkspace } from '@/features/meetings/components/MeetingWorkspace'
import { FixtureMeeting } from '@/features/meetings/components/FixtureMeeting'
import { RecordsPanel } from '@/features/records'
import { NotificationsPanel } from '@/features/notifications/components/NotificationsPanel'
import { useAuthStore } from '@/shared/auth/store'
import { Card } from '@/shared/ui/Card'
export default function MeetingsPage() {
  const { meetingId } = useParams()
  const [params] = useSearchParams()
  const meQuery = useMe()
  const linkedClub = useNotificationClub(params.get('clubId'))
  const { me, clubId, token } = useAuthStore()
  if (import.meta.env.DEV && params.get('fixture') === '1') return <FixtureMeeting />
  if (token && meQuery.isPending && !me)
    return <Card className="p-8">로그인과 소속을 확인 중입니다…</Card>
  if (token && me && !meQuery.isError && linkedClub.status === 'waiting')
    return <Card className="p-8">알림 항목의 소속을 확인 중입니다…</Card>
  if (linkedClub.status === 'error')
    return (
      <Card className="p-8 text-failed" role="alert">
        {linkedClub.error}
      </Card>
    )
  if (!me || !clubId || !me.clubs.some((c) => c.id === clubId))
    return (
      <Card className="space-y-3 p-8">
        <h1 className="text-h2">로그인과 소속 선택이 필요합니다.</h1>
        <p>회의와 자료, 알림은 선택한 소속 안에서 사용합니다.</p>
        <Link
          to={`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`}
          className="text-blue-700 underline"
        >
          로그인·소속 선택
        </Link>
        {import.meta.env.DEV && (
          <p>
            <Link to="/meetings?fixture=1" className="underline">
              개발 fixture 화면 열기
            </Link>
          </p>
        )}
      </Card>
    )
  return (
    <MeetingWorkspace
      key={`${clubId}:${meetingId ?? 'new'}`}
      clubId={clubId}
      meetingId={meetingId}
      highlightTaskId={params.get('taskId') ?? undefined}
      records={<RecordsPanel clubId={clubId} />}
      notifications={<NotificationsPanel key={me.id} />}
    />
  )
}
