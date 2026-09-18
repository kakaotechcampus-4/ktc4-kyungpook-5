import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/index.css'

// 세팅 확인용 임시 화면. app/router.tsx 가 붙으면 <Router /> 로 교체된다.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <main className="flex min-h-screen flex-col items-center justify-center gap-2">
      <h1 className="text-2xl font-semibold text-gray-900">운영해</h1>
      <p className="text-sm text-gray-500">
        API 서버: {import.meta.env.VITE_API_BASE_URL || '(VITE_API_BASE_URL 미설정)'}
      </p>
    </main>
  </StrictMode>,
)
