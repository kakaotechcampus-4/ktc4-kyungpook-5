import { Link } from 'react-router-dom'
import { useMe } from '@/features/auth/hooks'
import { RecordSearch, RecordsPanel } from '@/features/records'
import { useAuthStore } from '@/shared/auth/store'
import { Card } from '@/shared/ui/Card'
import { Button } from '@/shared/ui/Button'
import { Tori } from '@/shared/ui/Tori'

export default function RecordsPage() {
  const session = useMe()
  const { me, clubId, token } = useAuthStore()
  if (token && session.isPending && !me) return <Card className="p-8">소속을 확인하고 있어요…</Card>
  if (token && session.isError && !me)
    return (
      <Card className="space-y-3 p-8">
        <h1 className="text-h2">소속을 확인하지 못했어요</h1>
        <Button variant="secondary" onClick={() => void session.refetch()}>
          다시 확인
        </Button>
        <Link to="/login?next=%2Frecords" className="ml-3 text-blue-700 underline">
          로그인
        </Link>
      </Card>
    )
  if (!me || !clubId || !me.clubs.some((club) => club.id === clubId))
    return (
      <Card className="space-y-3 p-8">
        <h1 className="text-h2">자료함을 사용할 소속을 선택해 주세요</h1>
        <p>로그인한 소속의 자료를 모아두고 회의에서 함께 활용해요.</p>
        <Link to="/login?next=%2Frecords" className="inline-block text-blue-700 underline">
          로그인·소속 선택
        </Link>
      </Card>
    )
  const club = me.clubs.find((item) => item.id === clubId)!
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-caption text-mute">{club.name}</p>
          <h1 className="text-h1">자료함</h1>
          <p className="mt-2 text-ink2">
            회의에서 찾아볼 자료를 모아두고 검색 준비 상태를 확인해요.
          </p>
        </div>
        <Link
          to="/meetings"
          className="rounded-xl border border-soft bg-card px-4 py-2.5 text-caption font-bold text-ink2 hover:bg-bg"
        >
          회의로 이동
        </Link>
      </header>
      <RecordSearch key={`${me.id}:${clubId}`} clubId={clubId} userId={me.id} />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_240px]">
        <RecordsPanel key={clubId} clubId={clubId} title="자료 업로드·목록" />
        <Card className="space-y-3 p-5">
          <Tori size={40} />
          <h2 className="text-h3">회의에서 자료를 찾을 때</h2>
          <p className="text-caption leading-6 text-ink2">
            회칙, 행사 기록, 장부처럼 함께 참고할 문서를 올려 주세요. 검색 준비가 끝난 자료는 회의의
            답변과 출처에 활용할 수 있어요.
          </p>
          <p className="text-caption leading-6 text-mute">
            파일을 읽은 상태와 검색 준비 완료는 달라요. 자료 옆의 처리 상태를 확인해 주세요.
          </p>
        </Card>
      </div>
    </div>
  )
}
