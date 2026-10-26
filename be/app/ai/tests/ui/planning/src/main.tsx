// AI팀의 재현·협의용 앱. 제품 FE 라우터·로그인·API 클라이언트와 연결하지 않는다.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import PlanningPlaygroundPage from './pages/PlanningPlaygroundPage'
import { Tori } from './shared/ui/Tori'
import './styles/index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <header className="flex items-center gap-3 border-b border-line bg-card px-6 py-4">
      <Tori size={30} />
      <div>
        <p className="font-bold">운영해 · AI 계획 테스트</p>
        <p className="text-caption text-mute">AI 동작 재현 · BE/FE 협의 참고용 · 제품 화면 아님</p>
      </div>
    </header>
    <main className="mx-auto max-w-[1440px] px-5 py-7 sm:px-10">
      <PlanningPlaygroundPage />
    </main>
  </StrictMode>,
)
