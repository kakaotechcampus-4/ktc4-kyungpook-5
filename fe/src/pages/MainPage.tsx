import { Link } from 'react-router-dom'
import { useMe } from '@/features/auth/hooks'
import { liveStarters, respondFromServer, useBriefing } from '@/features/dashboard/briefing'
import { ToriDesk } from '@/features/dashboard/components/ToriDesk'
import { DEMO_BRIEFING, DEMO_STARTERS, demoRespond } from '@/features/dashboard/demoDesk'
import { useDemo } from '@/features/events/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

export default function MainPage() {
  // ?demo는 로그인 없이 예시 데이터로 본다.
  return useDemo() ? (
    <ToriDesk
      briefing={{ status: 'ready', data: DEMO_BRIEFING }}
      starters={DEMO_STARTERS}
      respond={demoRespond}
    />
  ) : (
    <LiveMainPage />
  )
}

function LiveMainPage() {
  const session = useMe()
  const { token, me } = useAuthStore()
  const clubId = useAuthStore((state) => state.clubId)
  const selectedClub = me?.clubs.find((club) => club.id === clubId)
  if (token && session.isPending && !me) {
    return <Card role="status" className="p-8">로그인과 소속을 확인하고 있어요…</Card>
  }
  if (token && session.isError && !me) {
    return (
      <Card role="alert" className="space-y-3 p-8">
        <h1 className="text-h2">로그인 정보를 확인하지 못했어요.</h1>
        <p className="text-caption text-mute">연결 상태를 확인하고 다시 시도해 주세요.</p>
        <Button variant="secondary" onClick={() => void session.refetch()}>
          다시 확인
        </Button>
      </Card>
    )
  }
  if (!token || !me || !clubId || !selectedClub) {
    return (
      <Card className="space-y-3 p-8">
        <h1 className="text-h2">로그인과 소속 선택이 필요합니다.</h1>
        <p className="text-caption text-mute">자료와 회의 답변은 선택한 소속 안에서 확인합니다.</p>
        <Link to="/login?next=%2Fdashboard" className="text-blue-700 underline">
          로그인·소속 선택
        </Link>
      </Card>
    )
  }
  // 소속을 바꾸면 대화를 새로 시작한다. 다른 소속의 답이 남지 않게 한다.
  return <LiveDesk key={`${me.id}:${clubId}`} clubId={clubId} userId={me.id} />
}

function LiveDesk({ clubId, userId }: { clubId: string; userId: string }) {
  const briefing = useBriefing(clubId, userId)
  return (
    <ToriDesk
      briefing={briefing}
      starters={liveStarters(briefing)}
      respond={(message, clarification) => respondFromServer(clubId, message, clarification)}
    />
  )
}
