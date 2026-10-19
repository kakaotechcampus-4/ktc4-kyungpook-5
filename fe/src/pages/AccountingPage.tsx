import { Link } from 'react-router-dom'
import { ExpensesPanel } from '@/features/accounting/components/ExpensesPanel'
import { useMe } from '@/features/auth/hooks'
import { useAuthStore } from '@/shared/auth/store'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

export default function AccountingPage() {
  const meQuery = useMe()
  const { token, me, clubId } = useAuthStore()
  const club = me?.clubs.find((item) => item.id === clubId)

  if (token && meQuery.isPending && !me) {
    return (
      <Card role="status" className="p-8">
        로그인과 소속을 확인하고 있어요…
      </Card>
    )
  }
  if (token && meQuery.isError) {
    return (
      <Card role="alert" className="space-y-3 p-8">
        <h1 className="text-h2">로그인 정보를 확인하지 못했어요.</h1>
        <p className="text-[13px] text-mute">연결 상태를 확인하고 다시 시도해 주세요.</p>
        <Button variant="secondary" onClick={() => void meQuery.refetch()}>
          다시 확인
        </Button>
      </Card>
    )
  }
  if (!token || !me || !clubId || !club) {
    return (
      <Card className="space-y-3 p-8">
        <h1 className="text-h2">로그인과 소속 선택이 필요합니다.</h1>
        <p className="text-[13px] text-mute">회계 내역은 선택한 팀 안에서 확인합니다.</p>
        <Link to="/login?next=%2Faccounting" className="text-blue-700 underline">
          로그인·소속 선택
        </Link>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex flex-col gap-[6px]">
        <h1 className="text-h1 text-ink">회계</h1>
        <p className="text-[13px] text-mute">{club.name}에 저장된 지출 내역을 확인합니다.</p>
      </header>
      <ExpensesPanel clubId={clubId} />
    </div>
  )
}
