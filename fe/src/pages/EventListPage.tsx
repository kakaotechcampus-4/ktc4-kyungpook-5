// L1 행사 목록: 계획 중 · 진행 중 · 끝난 행사를 모두 본다.
import { useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'

export default function EventListPage() {
  const navigate = useNavigate()
  const startPlanning = () => navigate('/planning')

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex items-center justify-between">
        <div className="flex flex-col gap-[4px]">
          <h1 className="text-h1">행사 목록</h1>
          <p className="text-mute">계획 중인 행사와 지난 행사를 모두 봅니다</p>
        </div>
        <Button size="lg" className="text-[13px]" onClick={startPlanning}>
          + 새 행사 만들기
        </Button>
      </header>

      <EmptyState
        toriSize={96}
        title="아직 만든 행사가 없어요"
        desc="행사를 만들면 여기에 쌓여요. 끝난 행사 기록도 여기서 다시 볼 수 있어요."
        action={
          <Button size="lg" className="text-[13px]" onClick={startPlanning}>
            첫 행사 만들기
          </Button>
        }
      />
    </div>
  )
}
