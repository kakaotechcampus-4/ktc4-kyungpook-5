// M1 메인(AI 비서): 진행 중인 행사에서 결정이 필요한 일만 모아 보여준다.
import { useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'

export default function MainPage() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex flex-col gap-[4px]">
        <h1 className="text-h1">AI 비서</h1>
        <p className="text-mute">결정이 필요한 일만 올려요. 승인한 일은 직접 진행해 주세요.</p>
      </header>

      <EmptyState
        title="아직 진행 중인 행사가 없어요"
        desc="행사 계획을 시작하면 제가 단계를 만들고, 승인이 필요한 일만 모아서 여기에 올려드릴게요."
        action={
          <Button size="lg" className="text-[13px]" onClick={() => navigate('/planning')}>
            행사 계획 시작하기
          </Button>
        }
      />
    </div>
  )
}
