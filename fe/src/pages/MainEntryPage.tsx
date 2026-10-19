import { Navigate } from 'react-router-dom'

// 메인은 목업 시작 화면을 유지한다. 예시 저장 여부로 실제 API 화면에 진입하지 않는다.
export default function MainEntryPage() {
  return <Navigate to="/onboarding" replace />
}
