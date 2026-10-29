import { Link } from 'react-router-dom'
import { useDashboardOverview } from '@/features/dashboard/overview'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Textarea } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'

const format = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul',
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(value))
    : '시간 미정'

export function ToriHome() {
  const { me, clubId } = useAuthStore()
  const overview = useDashboardOverview(clubId, me?.id)
  const items = overview.tasks.data?.filter((item) => item.status === 'ACTIVE') ?? []
  const schedules = items
    .filter((item) => item.kind === 'SCHEDULE')
    .sort((a, b) => (a.scheduledAt ?? '9999').localeCompare(b.scheduledAt ?? '9999'))
    .slice(0, 4)
  const mine = items
    .filter((item) => item.kind === 'TASK' && item.assigneeAccountId === me?.id)
    .sort((a, b) => (a.dueAt ?? '9999').localeCompare(b.dueAt ?? '9999'))
    .slice(0, 4)
  const showTasks = () => {
    if (!clubId) return <p>로그인하고 소속을 선택해 주세요.</p>
    if (overview.tasks.isPending) return <p role="status">불러오는 중이에요…</p>
    if (overview.tasks.isError)
      return (
        <p role="alert">
          불러오지 못했어요.{' '}
          <button className="underline" onClick={() => void overview.tasks.refetch()}>
            다시 시도
          </button>
        </p>
      )
    return null
  }
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <p className="text-caption text-mute">
          {me?.clubs.find((club) => club.id === clubId)?.name ?? '운영해'}
        </p>
        <h1 className="mt-1 text-h1">안녕하세요, 토리예요</h1>
        <p className="mt-2 text-ink2">회의와 행사 준비를 함께 살펴볼게요.</p>
      </header>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="flex min-h-[460px] flex-col p-5 sm:p-7">
          <div className="flex items-start gap-4">
            <Tori size={48} />
            <div>
              <h2 className="text-h2">무엇을 도와드릴까요?</h2>
              <p className="mt-2 text-caption leading-6 text-ink2">
                회의를 시작하거나 자료를 찾아볼 수 있어요. 자유롭게 질문하는 기능은 준비 중이에요.
              </p>
            </div>
          </div>
          <div className="my-7 grid gap-2 sm:grid-cols-2">
            <Link
              className="rounded-xl border border-soft p-4 text-left text-caption font-bold hover:bg-bg"
              to="/meetings"
            >
              지난 회의의 할 일을 확인하고 싶어요{' '}
              <span className="mt-1 block font-normal text-mute">
                회의 화면에서 저장된 항목 확인 →
              </span>
            </Link>
            <Link
              className="rounded-xl border border-soft p-4 text-left text-caption font-bold hover:bg-bg"
              to="/records"
            >
              행사 예산 관련 자료를 찾아줘{' '}
              <span className="mt-1 block font-normal text-mute">자료함에서 검색 →</span>
            </Link>
            <Link
              className="rounded-xl border border-soft p-4 text-left text-caption font-bold hover:bg-bg"
              to="/meetings"
            >
              새 회의를 시작할게요{' '}
              <span className="mt-1 block font-normal text-mute">회의 만들기 →</span>
            </Link>
          </div>
          <div className="mt-auto space-y-2 border-t border-line pt-4">
            <Textarea
              label="토리에게 질문"
              rows={2}
              disabled
              placeholder="자유 대화 연결 준비 중"
            />
            <p className="text-caption text-mute">
              자유 대화가 연결되면 Enter로 전송하고 Shift+Enter로 줄바꿈할 수 있어요.
            </p>
            <Button disabled>보내기</Button>
          </div>
        </Card>
        <aside className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
          <Card className="space-y-3 p-5">
            <div className="flex justify-between gap-2">
              <h2 className="text-h3">저장된 일정</h2>
              <Link className="text-caption text-blue-700 underline" to="/meetings">
                회의로
              </Link>
            </div>
            {showTasks()}
            {overview.tasks.isSuccess &&
              (schedules.length ? (
                <ul className="space-y-3">
                  {schedules.map((item) => (
                    <li key={item.id} className="text-caption">
                      <strong>{item.title}</strong>
                      <span className="mt-1 block text-mute">
                        {format(item.scheduledAt)} · 한국시간
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-caption text-mute">확인된 일정이 없어요.</p>
              ))}
          </Card>
          <Card className="space-y-3 p-5">
            <div className="flex justify-between gap-2">
              <h2 className="text-h3">내 할 일</h2>
              <Link className="text-caption text-blue-700 underline" to="/meetings">
                회의로
              </Link>
            </div>
            {showTasks()}
            {overview.tasks.isSuccess &&
              (mine.length ? (
                <ul className="space-y-3">
                  {mine.map((item) => (
                    <li key={item.id} className="text-caption">
                      <strong>{item.title}</strong>
                      <span className="mt-1 block text-mute">{format(item.dueAt)} · 한국시간</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-caption text-mute">계정에 배정된 할 일이 없어요.</p>
              ))}
            <p className="text-caption text-mute">
              담당자가 이름으로만 저장된 항목은 포함되지 않아요.
            </p>
          </Card>
          <Card className="space-y-3 p-5">
            <div className="flex justify-between gap-2">
              <h2 className="text-h3">진행 행사</h2>
              <Link className="text-caption text-blue-700 underline" to="/planning">
                계획하기
              </Link>
            </div>
            {!clubId ? (
              <p className="text-caption">로그인하고 소속을 선택해 주세요.</p>
            ) : overview.events.isPending ? (
              <p role="status" className="text-caption">
                불러오는 중이에요…
              </p>
            ) : overview.events.isError ? (
              <p role="alert" className="text-caption">
                행사를 불러오지 못했어요.{' '}
                <button className="underline" onClick={() => void overview.events.refetch()}>
                  다시 시도
                </button>
              </p>
            ) : overview.events.data?.data.length ? (
              <ul className="space-y-3">
                {overview.events.data.data.map((event) => (
                  <li key={event.id} className="text-caption">
                    <strong>{event.title}</strong>
                    <span className="mt-1 block text-mute">
                      {event.currentStepName ?? '진행 단계 미정'}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-caption text-mute">진행 중인 행사가 없어요.</p>
            )}
          </Card>
        </aside>
      </div>
    </div>
  )
}
