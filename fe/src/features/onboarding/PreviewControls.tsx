import { useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import type { useOnboarding } from './useOnboarding'

export function PreviewControls({ onboarding }: { onboarding: ReturnType<typeof useOnboarding> }) {
  const navigate = useNavigate()
  return (
    <div className="relative z-[70] mb-4 flex flex-wrap items-center justify-between gap-2">
      <p className="text-[11px] text-mute">목업 체험 · 실제 계정과 서버에는 반영되지 않아요</p>
      <div className="flex gap-1">
        <Button
          data-guide-toggle
          size="sm"
          variant="ghost"
          onClick={() => onboarding.update({ guideEnabled: !onboarding.state.guideEnabled })}
        >
          {onboarding.state.guideEnabled ? '안내 끄기' : '안내 켜기'}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          title="목업 진행만 지우고 로그인부터 다시 시작합니다"
          onClick={() => {
            onboarding.reset()
            navigate('/onboarding/login', { replace: true })
          }}
        >
          온보딩 초기화
        </Button>
        <Button
          size="sm"
          title="체험을 끝내고 실제 로그인 화면으로 나갑니다"
          onClick={() => navigate('/login')}
        >
          체험 끝내기
        </Button>
      </div>
    </div>
  )
}
