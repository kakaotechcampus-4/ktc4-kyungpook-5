// 없는 주소로 들어왔을 때. 앱 틀(상단바·탭)은 그대로 두고 본문만 바꾼다.
import { useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { StateScreen } from '@/shared/ui/StateScreen'

export default function NotFoundPage() {
  const navigate = useNavigate()
  return (
    <StateScreen
      title="없는 페이지예요"
      desc="주소가 바뀌었거나 없어진 화면이에요. 메인에서 다시 찾아 주세요."
    >
      <Button size="lg" className="text-[13px]" onClick={() => navigate('/')}>
        메인으로
      </Button>
    </StateScreen>
  )
}
